from django.contrib.auth import get_user_model
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

    def test_dashboard_only_counts_own_agency_ofws(self):
        self.client.force_login(self.staff_a)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['kpi']['ofw_total'], 1)
        self.assertContains(response, 'Alpha Agency')

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
