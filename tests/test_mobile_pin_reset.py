import unittest

from app.mobile_pin import pin_hash, pin_matches, valid_pin


class MobilePinResetTests(unittest.TestCase):
    def test_valid_four_digit_pin(self):
        self.assertTrue(valid_pin("1234"))

    def test_leading_zero_is_preserved(self):
        stored = pin_hash("0427")
        self.assertTrue(pin_matches("0427", stored))
        self.assertFalse(pin_matches("427", stored))

    def test_invalid_pin_lengths_and_characters(self):
        for value in ("", "123", "12345", "12A4", "12 4", "1-23"):
            self.assertFalse(valid_pin(value))

    def test_pin_hash_does_not_contain_plaintext(self):
        stored = pin_hash("9876")
        self.assertNotIn("9876", stored)
        self.assertTrue(pin_matches("9876", stored))
        self.assertFalse(pin_matches("1234", stored))


if __name__ == "__main__":
    unittest.main()
