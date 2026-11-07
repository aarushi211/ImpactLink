import unittest
from unittest.mock import Mock, patch
from services.ngo_store import register, update_profile


class OrganizationProfileTests(unittest.TestCase):
    def setUp(self):
        self.stored = {"id": "demo", "email": "demo@example.test", "org_name": "Demo", "geographic_focus": ["California", "Oregon"]}
        self.document = Mock()
        self.document.get.return_value.exists = True
        self.document.get.return_value.to_dict.side_effect = lambda: dict(self.stored)
        self.document.update.side_effect = self.stored.update
        self.db = Mock()
        self.db.collection.return_value.document.return_value = self.document
        self.patch = patch("services.ngo_store._get_db", return_value=self.db)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_new_profile_starts_with_setup_pending_and_collaboration_opted_out(self):
        result = register("new", "new@example.test", "New organization")
        self.assertFalse(result["onboarding_completed"])
        self.assertFalse(result["collab_open"])
        self.assertEqual(result["target_beneficiaries"], [])
        self.document.set.assert_called_once_with(result)

    def test_setup_updates_preserve_identity_and_preexisting_service_areas(self):
        result = update_profile("demo", {"org_name": " Updated organization ", "founding_year": 2017, "target_beneficiaries": ["Rural youth", " Rural youth "], "onboarding_completed": True, "email": "changed@example.test"})
        self.assertEqual(result["org_name"], "Updated organization")
        self.assertEqual(result["email"], "demo@example.test")
        self.assertEqual(result["geographic_focus"], ["California", "Oregon"])
        self.assertEqual(result["target_beneficiaries"], ["Rural youth"])
        self.assertEqual(result["founding_year"], 2017)
        self.assertTrue(result["onboarding_completed"])

    def test_invalid_values_do_not_write(self):
        for updates in ({"org_name": " "}, {"onboarding_completed": "yes"}, {"collab_open": 1}, {"founding_year": True}, {"founding_year": 3000}, {"target_beneficiaries": "a string"}):
            with self.subTest(updates=updates), self.assertRaises(ValueError):
                update_profile("demo", updates)
        self.document.update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
