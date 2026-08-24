import unittest
from washington_permits.models import Permit
from washington_permits.classify import classify_permit

class Tests(unittest.TestCase):
    def test_multifamily_new(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="1",issued_date="2026-08-01",permit_type="Multifamily / New",building_use="Residential",project_name="Construct new 12 unit apartment",units=12,raw={"permitclass":"Multifamily","permittypedesc":"New","description":"Construct new 12 unit apartment"})
        classify_permit(p); self.assertTrue(p.qualifies); self.assertEqual(p.classification,"MULTIFAMILY")

    def test_single_family_new(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="2",issued_date="2026-08-01",permit_type="Single Family/Duplex / New",project_name="Construct one family dwelling",raw={"permitclass":"Single Family/Duplex","permittypedesc":"New","description":"Construct one family dwelling"})
        classify_permit(p); self.assertEqual(p.classification,"SINGLE_FAMILY")

    def test_two_family_in_shared_class_is_multifamily(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="4",issued_date="2026-08-20",permit_type="Single Family/Duplex / New",project_name="Construct new East two family dwelling (duplex 1) per plan",units=2,raw={"permitclass":"Single Family/Duplex","permittypedesc":"New","description":"Construct new East two family dwelling (duplex 1) per plan"})
        classify_permit(p); self.assertTrue(p.qualifies); self.assertEqual(p.classification,"MULTIFAMILY")

    def test_two_family_phrase_without_duplex_word_is_multifamily(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="5",issued_date="2026-08-19",permit_type="Single Family/Duplex / New",project_name="Construct new east two-family dwelling per plan",units=2,raw={"permitclass":"Single Family/Duplex","permittypedesc":"New","description":"Construct new east two-family dwelling per plan"})
        classify_permit(p); self.assertEqual(p.classification,"MULTIFAMILY")

    def test_remodel_excluded(self):
        p=Permit(state="WA",jurisdiction="Seattle",permit_number="3",issued_date="2026-08-01",permit_type="Commercial / Addition/Alteration",raw={"permitclass":"Commercial","permittypedesc":"Addition/Alteration","description":"tenant improvement"})
        classify_permit(p); self.assertFalse(p.qualifies)

if __name__=="__main__": unittest.main()
