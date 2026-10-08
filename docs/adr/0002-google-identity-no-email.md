# Google identity, and no email at all

All identity comes from Google OAuth and the system sends no email of any kind,
which rules out passwords and magic links. The consequence worth recording:
invitations cannot be delivered by the product, so an invitation is simply a
membership row keyed on an email address that nobody has signed in with yet —
there is no Invite entity and no token — and the link to the actual person is
made by hand in a group chat. This kept email deliverability, domain
verification, and password reset flows entirely out of the project.
