import threading
from unittest import mock

from allauth.account.models import EmailAddress
from allauth.core import context
from allauth.socialaccount.adapter import get_adapter
from allauth.socialaccount.helpers import complete_social_login
from django.contrib.auth.models import AnonymousUser
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import reverse

from accounts.models import User
from boards.forms import CardForm
from boards.models import Board, Card, Membership, lock_membership

from .test_cards import a_card, a_user


def verified(user):
    """As Google's sign-in records it: the address, verified."""
    EmailAddress.objects.create(user=user, email=user.email, verified=True, primary=True)
    return user


def sign_in_with_google(email, verified=True):
    """Run allauth's own Google sign-in pipeline on a userinfo payload, so the
    claim is tested through the real sign-in rather than a hand-made user."""
    request = RequestFactory().get("/")
    SessionMiddleware(lambda r: None).process_request(request)
    MessageMiddleware(lambda r: None).process_request(request)
    request.user = AnonymousUser()
    payload = {
        "sub": email,
        "email": email,
        "email_verified": verified,
        "given_name": "Grace",
        "family_name": "Hopper",
    }
    # allauth's middleware normally provides the request this way.
    with context.request_context(request):
        provider = get_adapter().get_provider(request, "google")
        sociallogin = provider.sociallogin_from_response(request, payload)
        complete_social_login(request, sociallogin)
    return User.objects.get(email__iexact=email)


class InvitingTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.client.force_login(self.ada)
        self.members_url = reverse("board_members", args=[self.board.pk])
        self.board_url = reverse("board_detail", args=[self.board.pk])

    def invite(self, email):
        return self.client.post(reverse("member_invite", args=[self.board.pk]), {"email": email})

    def text(self, url):
        return " ".join(self.client.get(url).content.decode().split())

    def test_the_board_menu_leads_to_the_members_page(self):
        content = self.text(self.board_url)

        self.assertIn(f'href="{self.members_url}"', content)
        self.assertIn("ada@example.com", self.text(self.members_url))

    def test_an_owner_invites_by_email_creating_a_pending_member(self):
        response = self.invite("grace@example.com")

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        pending = self.board.memberships.get(user__isnull=True)
        self.assertEqual((pending.email, pending.role), ("grace@example.com", "member"))
        content = self.text(self.members_url)
        self.assertIn("Invited grace@example.com.", content)
        self.assertIn("Invited, not signed in yet", content)

    def test_a_pending_member_grants_no_access(self):
        self.invite("grace@example.com")
        # Signed in with that address, but not verified, so nothing is claimed.
        grace = a_user("grace@example.com")
        self.client.force_login(grace)

        self.assertEqual(self.client.get(self.board_url).status_code, 404)
        self.assertNotIn("Housework", self.text(reverse("home")))

    def test_signing_in_with_google_on_that_address_claims_it_ignoring_case(self):
        self.invite("Grace@Example.com")

        grace = sign_in_with_google("grace@example.com")

        membership = self.board.memberships.get(user=grace)
        self.assertEqual((membership.email, membership.role), ("", "member"))
        self.assertFalse(self.board.memberships.filter(user__isnull=True).exists())
        self.client.force_login(grace)
        self.assertEqual(self.client.get(self.board_url).status_code, 200)

    def test_an_address_google_has_not_verified_claims_nothing(self):
        self.invite("grace@example.com")

        sign_in_with_google("grace@example.com", verified=False)

        self.assertTrue(self.board.memberships.filter(user__isnull=True).exists())

    def test_someone_already_signed_in_claims_it_on_the_home_page(self):
        grace = verified(a_user("grace@example.com"))
        graces_browser = self.client_class()
        graces_browser.force_login(grace)  # signed in before the invitation
        self.invite("grace@example.com")

        content = graces_browser.get(reverse("home")).content.decode()

        self.assertIn("Housework", content)
        self.assertTrue(self.board.memberships.filter(user=grace).exists())

    def test_an_invitation_for_someone_already_a_member_by_then_just_goes(self):
        grace = verified(a_user("grace@example.com"))
        Membership.objects.create(board=self.board, email="grace@example.com")
        Membership.objects.create(board=self.board, user=grace)

        Membership.objects.claim_for(grace)

        self.assertEqual(self.board.memberships.filter(user=grace).count(), 1)
        self.assertFalse(self.board.memberships.filter(user__isnull=True).exists())

    def test_inviting_a_member_or_an_invited_address_again_makes_no_duplicate(self):
        grace = a_user("grace@example.com")
        Membership.objects.create(board=self.board, user=grace)
        self.invite("hopper@example.com")

        for email, reason in [
            ("GRACE@example.com", "GRACE@example.com is already a Member of this board."),
            ("ada@EXAMPLE.com", "ada@EXAMPLE.com is already a Member of this board."),
            ("Hopper@example.com", "Hopper@example.com has already been invited."),
        ]:
            with self.subTest(email=email):
                response = self.invite(email)
                self.assertEqual(response.status_code, 400)
                self.assertContains(response, reason, status_code=400)
        self.assertEqual(self.board.memberships.count(), 3)

    def test_the_database_refuses_a_second_invitation_for_an_address(self):
        Membership.objects.create(board=self.board, email="grace@example.com")

        with self.assertRaises(IntegrityError), transaction.atomic():
            Membership.objects.create(board=self.board, email="GRACE@example.com")

    def test_the_database_refuses_a_membership_both_or_neither_claimed(self):
        for fields in [{}, {"user": a_user("grace@example.com"), "email": "grace@example.com"}]:
            with self.subTest(fields=fields):
                with self.assertRaises(IntegrityError), transaction.atomic():
                    Membership.objects.create(board=self.board, **fields)

    def test_the_owner_can_withdraw_an_invitation(self):
        self.invite("grace@example.com")
        pending = self.board.memberships.get(user__isnull=True)

        self.client.post(reverse("member_remove", args=[self.board.pk, pending.pk]))

        self.assertFalse(self.board.memberships.filter(user__isnull=True).exists())
        self.assertIn("Withdrew the invitation for grace@example.com.", self.text(self.members_url))

    def test_only_the_owner_invites_or_withdraws(self):
        grace = a_user("grace@example.com")
        Membership.objects.create(board=self.board, user=grace)
        pending = Membership.objects.create(board=self.board, email="hopper@example.com")
        self.client.force_login(grace)

        invite = self.invite("someone@example.com")
        withdraw = self.client.post(reverse("member_remove", args=[self.board.pk, pending.pk]))
        page = self.text(self.members_url)

        self.assertEqual((invite.status_code, withdraw.status_code), (403, 403))
        self.assertEqual(self.board.memberships.count(), 3)
        self.assertNotIn("Invite someone", page)
        self.assertNotIn(">Withdraw<", page)
        self.assertIn("hopper@example.com", page)

    def test_a_non_member_sees_nothing_of_the_members(self):
        self.client.force_login(a_user("grace@example.com"))

        for response in [self.client.get(self.members_url), self.invite("x@example.com")]:
            self.assertEqual(response.status_code, 404)

    def test_someone_with_no_boards_is_shown_the_address_they_signed_in_with(self):
        self.client.force_login(a_user("grace.hopper@example.com"))

        content = self.text(reverse("home"))

        self.assertIn("You have no boards yet.", content)
        self.assertIn('signed in as <span class="font-semibold text-text">grace.hopper@example.com</span>', content)


class RemovingTests(TestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)
        self.membership = Membership.objects.create(board=self.board, user=self.grace)
        self.to_do = self.board.stages.first()
        self.client.force_login(self.ada)
        self.members_url = reverse("board_members", args=[self.board.pk])

    def remove(self, membership):
        return self.client.post(reverse("member_remove", args=[self.board.pk, membership.pk]))

    def test_a_removed_member_loses_access_at_once(self):
        self.remove(self.membership)

        self.client.force_login(self.grace)
        response = self.client.get(reverse("board_detail", args=[self.board.pk]))
        self.assertEqual(response.status_code, 404)

    def test_their_assignments_are_cleared_archived_cards_included(self):
        on_board = a_card(self.to_do, "On the board", assignee=self.grace)
        archived = a_card(self.to_do, "Archived", assignee=self.grace)
        archived.archive()
        someone_elses = a_card(self.to_do, "Ada's own", assignee=self.ada)
        other_board = Board.objects.create_with_owner(name="Elsewhere", owner=self.ada)
        Membership.objects.create(board=other_board, user=self.grace)
        elsewhere = a_card(other_board.stages.first(), "Elsewhere", assignee=self.grace)

        self.remove(self.membership)

        for card, assignee in [
            (on_board, None),
            (archived, None),
            (someone_elses, self.ada),
            (elsewhere, self.grace),
        ]:
            card.refresh_from_db()
            self.assertEqual(card.assignee, assignee, card.title)
        content = " ".join(self.client.get(self.members_url).content.decode().split())
        self.assertIn("Removed grace. 2 Cards they were assigned are now unassigned.", content)

    def test_cards_they_created_still_credit_them(self):
        card = a_card(self.to_do, "Theirs", creator=self.grace)

        self.remove(self.membership)

        card.refresh_from_db()
        self.assertEqual(card.creator, self.grace)

    def test_a_removed_person_can_be_invited_again_and_claim_it(self):
        verified(self.grace)
        self.remove(self.membership)

        self.client.post(reverse("member_invite", args=[self.board.pk]), {"email": "grace@example.com"})
        Membership.objects.claim_for(self.grace)

        self.assertTrue(self.board.memberships.filter(user=self.grace).exists())

    def test_removing_is_confirmed_stating_how_many_cards_become_unassigned(self):
        a_card(self.to_do, "One", assignee=self.grace)
        a_card(self.to_do, "Two", assignee=self.grace)

        content = " ".join(self.client.get(self.members_url).content.decode().split())

        self.assertIn(f'commandfor="remove-member-{self.membership.pk}"', content)
        self.assertIn("Remove grace?</h2>", content)
        self.assertIn("The 2 Cards assigned to them will become unassigned", content)

    def test_a_member_cannot_remove_another_member(self):
        hopper = a_user("hopper@example.com")
        other = Membership.objects.create(board=self.board, user=hopper)
        self.client.force_login(self.grace)

        response = self.remove(other)

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Membership.objects.filter(pk=other.pk).exists())

    def test_nobody_can_remove_the_owner(self):
        owner = self.board.memberships.get(user=self.ada)

        response = self.remove(owner)

        self.assertRedirects(response, self.members_url, fetch_redirect_response=False)
        self.assertTrue(Membership.objects.filter(pk=owner.pk).exists())
        self.assertIn("The Owner cannot be removed.", self.client.get(self.members_url).content.decode())
        self.assertNotIn(f"remove-member-{owner.pk}", self.client.get(self.members_url).content.decode())

    def test_a_card_saved_naming_someone_removed_meanwhile_is_refused(self):
        card = a_card(self.to_do, "Buy milk")
        is_valid = CardForm.is_valid

        def removed_meanwhile(form):
            valid = is_valid(form)  # Grace was still a Member when checked
            Membership.objects.get(pk=self.membership.pk).remove()
            return valid

        with mock.patch.object(CardForm, "is_valid", removed_meanwhile):
            edit = self.client.post(
                reverse("card_edit", args=[self.board.pk, card.pk]),
                {"title": "Buy milk", "assignee": self.grace.pk},
            )

        self.assertContains(edit, "grace is no longer a Member of this board.", status_code=400)
        card.refresh_from_db()
        self.assertIsNone(card.assignee)

    def test_a_new_card_naming_someone_removed_meanwhile_is_refused(self):
        is_valid = CardForm.is_valid

        def removed_meanwhile(form):
            valid = is_valid(form)
            Membership.objects.get(pk=self.membership.pk).remove()
            return valid

        with mock.patch.object(CardForm, "is_valid", removed_meanwhile):
            response = self.client.post(
                reverse("card_create", args=[self.board.pk]),
                {"title": "Buy milk", "assignee": self.grace.pk},
            )

        self.assertContains(response, "grace is no longer a Member of this board.")
        self.assertFalse(Card.objects.exists())


class ConcurrentRemovalTests(TransactionTestCase):
    def setUp(self):
        self.ada = a_user()
        self.grace = a_user("grace@example.com")
        self.board = Board.objects.create_with_owner(name="Housework", owner=self.ada)

    def run_together(self, *actions):
        start = threading.Barrier(len(actions))
        outcomes = [None] * len(actions)

        def run(i, action):
            try:
                start.wait()
                action()
            except Exception as error:
                outcomes[i] = error
            finally:
                connection.close()

        threads = [threading.Thread(target=run, args=(i, a)) for i, a in enumerate(actions)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return outcomes

    def test_a_removal_and_a_save_naming_them_never_leave_a_card_on_a_non_member(self):
        for _ in range(10):
            membership = Membership.objects.create(board=self.board, user=self.grace)
            card = a_card(self.board.stages.first(), "Contested")

            def assign():
                with transaction.atomic():
                    lock_membership(self.board, self.grace)
                    Card.objects.filter(pk=card.pk).update(assignee=self.grace)

            remove, save = self.run_together(
                lambda: Membership.objects.get(pk=membership.pk).remove(), assign
            )

            self.assertIsNone(remove)
            self.assertTrue(save is None or isinstance(save, Membership.DoesNotExist), save)
            card.refresh_from_db()
            self.assertIsNone(card.assignee)
            Card.objects.all().delete()
