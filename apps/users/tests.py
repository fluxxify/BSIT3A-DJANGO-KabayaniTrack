from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

User = get_user_model()


class UserManagementAccessTests(TestCase):
    """Only administrators may manage accounts; staff is blocked."""

    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='rootadmin', email='rootadmin@example.com', password='Passw0rd!23'
        )
        self.staff = User.objects.create_user(
            username='staffmember', password='Passw0rd!23', is_staff=True
        )
        self.ofw = User.objects.create_user(
            username='plainofw', password='Passw0rd!23'
        )

    def test_admin_can_reach_user_list_page(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 200)

    def test_staff_is_redirected_from_user_list_page(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse('dashboard')))

    def test_ofw_is_redirected_from_user_list_page(self):
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('users:user_list'))
        self.assertEqual(response.status_code, 302)

    def test_staff_cannot_reach_user_ajax_endpoints(self):
        self.client.force_login(self.staff)
        self.assertEqual(
            self.client.get(reverse('users:user_get_ajax', args=[self.ofw.pk])).status_code,
            302,
        )
        self.assertEqual(
            self.client.post(
                reverse('users:user_delete_ajax', args=[self.ofw.pk])
            ).status_code,
            302,
        )
        self.assertTrue(User.objects.filter(pk=self.ofw.pk).exists())

    def test_admin_can_view_regular_user(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_can_view_superuser(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('users:user_get_ajax', args=[self.admin.pk]))
        self.assertEqual(response.status_code, 200)

    def test_admin_cannot_delete_self(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('users:user_delete_ajax', args=[self.admin.pk])
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_admin_can_change_user_password(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('users:user_save_ajax'), {
            'id': self.ofw.pk,
            'username': self.ofw.username,
            'first_name': self.ofw.first_name,
            'last_name': self.ofw.last_name,
            'email': self.ofw.email,
            'password': 'NewPassw0rd!23',
            'is_active': 'true',
            'is_staff': 'false',
        })
        self.assertEqual(response.status_code, 200)
        self.ofw.refresh_from_db()
        self.assertTrue(self.ofw.check_password('NewPassw0rd!23'))
        self.assertFalse(self.ofw.check_password('Passw0rd!23'))


class AgencyWorkspaceTests(TestCase):
    """Agency links, registration assignment and scoped dashboards."""

    def setUp(self):
        from apps.ofw.models import OFWProfile
        from apps.users.models import Agency, AgencyStaff

        cache.clear()
        self.Agency = Agency
        self.AgencyStaff = AgencyStaff
        self.OFWProfile = OFWProfile

        self.agency_a = Agency.objects.create(name='Alpha Agency', slug='alpha')
        self.agency_b = Agency.objects.create(name='Beta Agency', slug='beta')

        self.staff_a = User.objects.create_user(
            username='alpha_staff', password='Passw0rd!23', is_staff=True,
        )
        AgencyStaff.objects.create(user=self.staff_a, agency=self.agency_a)

        self.ofw_a = self.OFWProfile.objects.create(
            first_name='Ana', last_name='Alpha', agency_org=self.agency_a,
        )
        self.ofw_b = self.OFWProfile.objects.create(
            first_name='Ben', last_name='Beta', agency_org=self.agency_b,
        )

    def test_landing_page_shows_agency_and_portal_links(self):
        response = self.client.get(
            reverse('agency_landing', args=[self.agency_a.slug])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.agency_a.name)
        self.assertContains(response, 'dh-auth-bg')
        self.assertContains(
            response, reverse('agency_register', args=[self.agency_a.slug])
        )

    def test_registration_through_agency_link_assigns_agency(self):
        response = self.client.post(
            reverse('agency_register', args=[self.agency_a.slug]),
            {
                'username': 'agency_new_ofw',
                'first_name': 'Nico',
                'last_name': 'Cruz',
                'email': 'agency_new_ofw@example.com',
                'password': 'Str0ngPassw0rd!',
                'confirm_password': 'Str0ngPassw0rd!',
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = self.OFWProfile.objects.get(
            user__username='agency_new_ofw',
        )
        self.assertEqual(profile.agency_org, self.agency_a)
        self.assertEqual(profile.agency, self.agency_a.name)

    def test_generic_registration_lists_active_agencies(self):
        response = self.client.get(reverse('register'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agency / Partner Office')
        self.assertContains(response, self.agency_a.name)

    def test_generic_registration_can_choose_an_agency(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'public_new_ofw',
                'first_name': 'Mia',
                'last_name': 'Lopez',
                'email': 'public_new_ofw@example.com',
                'password': 'Str0ngPassw0rd!',
                'confirm_password': 'Str0ngPassw0rd!',
                'agency': str(self.agency_a.pk),
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = self.OFWProfile.objects.get(user__username='public_new_ofw')
        self.assertEqual(profile.agency_org, self.agency_a)
        self.assertEqual(profile.agency, self.agency_a.name)

    def test_generic_registration_without_agency_still_works(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'independent_ofw',
                'first_name': 'Noel',
                'last_name': 'Reyes',
                'email': 'independent_ofw@example.com',
                'password': 'Str0ngPassw0rd!',
                'confirm_password': 'Str0ngPassw0rd!',
            },
        )

        self.assertEqual(response.status_code, 302)
        profile = self.OFWProfile.objects.get(user__username='independent_ofw')
        self.assertIsNone(profile.agency_org)

    def test_generic_registration_rejects_inactive_agency(self):
        self.agency_a.is_active = False
        self.agency_a.save(update_fields=['is_active'])

        response = self.client.post(
            reverse('register'),
            {
                'username': 'inactive_agency_ofw',
                'first_name': 'Rina',
                'last_name': 'Cruz',
                'email': 'inactive_agency_ofw@example.com',
                'password': 'Str0ngPassw0rd!',
                'confirm_password': 'Str0ngPassw0rd!',
                'agency': str(self.agency_a.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Choose a valid agency')
        self.assertFalse(
            self.OFWProfile.objects.filter(
                user__username='inactive_agency_ofw'
            ).exists()
        )

    def test_dashboard_only_counts_own_agency_ofws(self):
        self.client.force_login(self.staff_a)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['kpi']['ofw_total'], 1)
        self.assertContains(response, 'Alpha Agency')

    def test_agency_staff_contact_is_visible_and_deletable(self):
        from apps.ofw.models import EmergencyContact

        self.client.force_login(self.staff_a)
        create = self.client.post(reverse('ofw:contact_save_ajax'), {
            'name': 'Alpha Hotline',
            'contact_type': 'owwa',
            'phone': '09170000000',
        })

        self.assertEqual(create.status_code, 200)
        contact = EmergencyContact.objects.get(name='Alpha Hotline')
        self.assertIsNone(contact.user_id)

        listing = self.client.get(
            reverse('ofw:contact_list_ajax'), {'q': 'Alpha'}
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.json()['total'], 1)

        delete = self.client.post(
            reverse('ofw:contact_delete_ajax', args=[contact.pk])
        )
        self.assertEqual(delete.status_code, 200)
        self.assertFalse(EmergencyContact.objects.filter(pk=contact.pk).exists())

    def test_agency_staff_cannot_open_other_agency_ofw(self):
        self.client.force_login(self.staff_a)

        allowed = self.client.get(
            reverse('ofw:profile_detail', args=[self.ofw_a.pk])
        )
        blocked = self.client.get(
            reverse('ofw:profile_detail', args=[self.ofw_b.pk])
        )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(blocked.status_code, 404)

    def test_superuser_still_sees_every_agency(self):
        admin = User.objects.create_superuser(
            username='agency_root', email='root@example.com',
            password='Passw0rd!23',
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['kpi']['ofw_total'], 2)

    def test_agency_staff_cannot_acknowledge_or_escalate_other_agency_alert(self):
        from apps.ofw.models import EmergencyAlert

        alert = EmergencyAlert.objects.create(
            ofw=self.ofw_b, title='Private agency alert'
        )
        self.client.force_login(self.staff_a)

        acknowledge = self.client.post(
            reverse('ofw:acknowledge_alert', args=[alert.pk])
        )
        escalate = self.client.post(
            reverse('ofw:escalate_to_police', args=[alert.pk])
        )

        self.assertEqual(acknowledge.status_code, 404)
        self.assertEqual(escalate.status_code, 404)
        alert.refresh_from_db()
        self.assertEqual(alert.status, EmergencyAlert.Status.OPEN)

    def test_agency_staff_cannot_submit_other_agency_police_report(self):
        from apps.ofw.models import PoliceReport

        report = PoliceReport.objects.create(
            ofw=self.ofw_b, title='Private report', reported_by=self.staff_a,
        )
        self.client.force_login(self.staff_a)
        response = self.client.post(
            reverse('ofw:police_report_submit', args=[report.pk]),
            {'police_station': 'Station', 'police_contact': '123'},
        )

        self.assertEqual(response.status_code, 404)
        report.refresh_from_db()
        self.assertEqual(report.status, PoliceReport.Status.DRAFT)

    def test_ofw_cannot_disable_safe_location(self):
        from apps.ofw.models import SafeLocation

        location = SafeLocation.objects.create(name='Test location', country='Qatar')
        ofw_user = User.objects.create_user(username='ordinary_ofw')
        self.client.force_login(ofw_user)
        response = self.client.post(
            reverse('ofw:safe_location_delete', args=[location.pk])
        )

        self.assertEqual(response.status_code, 403)
        location.refresh_from_db()
        self.assertTrue(location.is_active)
