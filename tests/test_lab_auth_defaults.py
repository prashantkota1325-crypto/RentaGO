import os
import unittest
from unittest.mock import patch

from app.routes.auth import _needs_email_mfa


class LabAuthDefaultsTests(unittest.TestCase):
    def test_development_mfa_is_opt_in(self):
        with patch.dict(os.environ, {"RENTAGO_EMAIL_MFA_ENABLED": "false"}, clear=False):
            self.assertFalse(_needs_email_mfa("super admin"))

    def test_development_mfa_can_be_explicitly_enabled(self):
        with patch.dict(os.environ, {"RENTAGO_EMAIL_MFA_ENABLED": "true"}, clear=False):
            self.assertTrue(_needs_email_mfa("super admin"))


if __name__ == "__main__":
    unittest.main()
