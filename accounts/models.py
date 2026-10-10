from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    """Keys users on email, because the system has no usernames.

    Email is the identity everywhere: a Pending member is a membership row
    carrying an email address that no user has signed in with yet, so the
    uniqueness of this column is what makes claiming an invitation possible.
    """

    use_in_migrations = True

    def create_user(self, email, **extra_fields):
        if not email:
            raise ValueError("A user must have an email address.")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_unusable_password()
        user.save(using=self._db)
        return user


class User(AbstractUser):
    """A person who has signed in. Identity always comes from Google.

    No password is ever stored: `set_unusable_password` leaves a value Django
    can never match against any input.
    """

    username = None
    first_name = None
    last_name = None

    email = models.EmailField(unique=True)
    display_name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Taken from the Google profile on first sign-in; editable after.",
    )

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    def __str__(self):
        return self.display_name or self.email

    @property
    def name(self):
        """What to call this person. Falls back to the email when unnamed."""
        return self.display_name or self.email
