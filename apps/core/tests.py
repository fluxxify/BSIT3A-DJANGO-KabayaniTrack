import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.ofw.models import Notification, OFWProfile


TEMP_MEDIA_DIR = tempfile.mkdtemp(prefix='kabayani_core_media_')


class MediaServingTests(TestCase):
    """Media is served with range support so browsers can play videos."""

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_DIR, ignore_errors=True)

    def setUp(self):
        self.video_path = os.path.join(TEMP_MEDIA_DIR, 'proof.mp4')
        with open(self.video_path, 'wb') as handle:
            handle.write(b'0123456789')

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_full_request_returns_whole_file(self):
        response = self.client.get(reverse('media', args=['proof.mp4']))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(response['Content-Length'], '10')
        self.assertEqual(b''.join(response.streaming_content), b'0123456789')

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_range_request_returns_partial_content(self):
        response = self.client.get(
            reverse('media', args=['proof.mp4']),
            headers={'range': 'bytes=2-5'},
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 2-5/10')
        self.assertEqual(response['Content-Length'], '4')
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(b''.join(response.streaming_content), b'2345')

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_suffix_range_request_returns_tail(self):
        response = self.client.get(
            reverse('media', args=['proof.mp4']),
            headers={'range': 'bytes=-3'},
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 7-9/10')
        self.assertEqual(b''.join(response.streaming_content), b'789')

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_range_beyond_file_returns_416(self):
        response = self.client.get(
            reverse('media', args=['proof.mp4']),
            headers={'range': 'bytes=50-60'},
        )

        self.assertEqual(response.status_code, 416)
        self.assertEqual(response['Content-Range'], 'bytes */10')

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_missing_file_returns_404(self):
        response = self.client.get(reverse('media', args=['nope.mp4']))

        self.assertEqual(response.status_code, 404)

    @override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
    def test_path_traversal_is_blocked(self):
        response = self.client.get(reverse('media', args=['../secret.txt']))

        self.assertEqual(response.status_code, 404)


class HomeViewTests(TestCase):
    def test_home_renders_for_authenticated_user(self):
        user = get_user_model().objects.create_user(
            username='admin', password='secret1234', is_staff=True
        )

        self.client.force_login(user)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'home.html')

    def test_home_requires_login(self):
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 302)


class OFWRegistrationTests(TestCase):
    def test_registration_creates_profile_and_redirects_to_portal(self):
        response = self.client.post(reverse('register'), {
            'username': 'newofw',
            'first_name': 'Nico',
            'last_name': 'Cruz',
            'email': 'nico@example.com',
            'password': 'Str0ngPassw0rd!',
            'confirm_password': 'Str0ngPassw0rd!',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))

        user = get_user_model().objects.get(username='newofw')
        self.assertTrue(user.ofw_profiles.exists())
        self.assertTrue(user.groups.filter(name='OFW').exists())

    def test_registration_notifies_managers_and_links_profile(self):
        staff = get_user_model().objects.create_user(
            username='registration_manager',
            password='Str0ngPassw0rd!',
            is_staff=True,
        )

        response = self.client.post(reverse('register'), {
            'username': 'phoneofw',
            'first_name': 'Maria',
            'last_name': 'Santos',
            'email': 'maria@example.com',
            'password': 'Str0ngPassw0rd!',
            'confirm_password': 'Str0ngPassw0rd!',
        })

        self.assertEqual(response.status_code, 302)
        profile = OFWProfile.objects.get(user__username='phoneofw')
        self.assertEqual(profile.country, '')

        notification = Notification.objects.get(
            recipient=staff,
            title__startswith='New OFW registered',
        )
        self.assertEqual(notification.level, Notification.Level.SUCCESS)
        self.assertEqual(
            notification.url,
            reverse('ofw:profile_detail', args=[profile.pk]),
        )
        self.assertIn('phoneofw', notification.message)
        self.assertIn('not set', notification.message)

    def test_registration_sends_welcome_notification(self):
        response = self.client.post(reverse('register'), {
            'username': 'welcomeofw',
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'email': 'ana@example.com',
            'password': 'Str0ngPassw0rd!',
            'confirm_password': 'Str0ngPassw0rd!',
        })

        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='welcomeofw')
        notification = Notification.objects.get(
            recipient=user,
            title='Welcome to KabayaniTrack',
        )
        self.assertEqual(notification.url, reverse('ofw:portal_profile'))
        self.assertEqual(notification.level, Notification.Level.INFO)

    def test_new_registration_appears_on_management_dashboard(self):
        staff = get_user_model().objects.create_user(
            username='dashboard_manager',
            password='Str0ngPassw0rd!',
            is_staff=True,
        )
        ofw = get_user_model().objects.create_user(
            username='dashboardofw',
            password='Str0ngPassw0rd!',
        )
        OFWProfile.objects.create(
            user=ofw,
            first_name='Maria',
            last_name='Santos',
            country='',
        )

        self.client.force_login(staff)
        response = self.client.get(reverse('dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Recent OFW Registrations')
        self.assertContains(response, 'Maria Santos')
        self.assertContains(response, 'dashboardofw')
        self.assertContains(response, 'Not set')

    def test_new_registration_appears_in_django_admin(self):
        admin_user = get_user_model().objects.create_superuser(
            username='registration_admin',
            email='admin@example.com',
            password='Str0ngPassw0rd!',
        )
        ofw = get_user_model().objects.create_user(
            username='adminvisibleofw',
            password='Str0ngPassw0rd!',
        )
        OFWProfile.objects.create(
            user=ofw,
            first_name='Maria',
            last_name='Santos',
            country='',
        )

        self.client.force_login(admin_user)
        response = self.client.get(reverse('admin:kabayan_ofwprofile_changelist'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Santos')
        self.assertContains(response, 'adminvisibleofw')

    def test_ofw_is_redirected_from_dashboard_to_portal(self):
        user = get_user_model().objects.create_user(
            username='ofwlogin', password='Str0ngPassw0rd!'
        )
        self.client.force_login(user)

        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))

    def test_ofw_login_redirects_to_portal(self):
        get_user_model().objects.create_user(
            username='ofwlogin2', password='Str0ngPassw0rd!'
        )

        response = self.client.post(reverse('login'), {
            'username': 'ofwlogin2',
            'password': 'Str0ngPassw0rd!',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ofw:portal'))


class LoginRoutingTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='boss', email='boss@example.com', password='Str0ngPassw0rd!'
        )
        self.staff = get_user_model().objects.create_user(
            username='crew', password='Str0ngPassw0rd!', is_staff=True
        )
        self.ofw = get_user_model().objects.create_user(
            username='biboy', password='Str0ngPassw0rd!'
        )

    def test_each_role_logs_in_without_account_type(self):
        for username, redirect_name in (
            ('boss', 'dashboard'),
            ('crew', 'dashboard'),
            ('biboy', 'ofw:portal'),
        ):
            response = self.client.post(reverse('login'), {
                'username': username,
                'password': 'Str0ngPassw0rd!',
            })
            self.assertEqual(response.status_code, 302, username)
            self.assertEqual(response.url, reverse(redirect_name))
            self.client.logout()


class ManagementSidebarTests(TestCase):
    """Administrators see account/directory links; staff only sees OFW monitoring."""

    def setUp(self):
        self.admin = get_user_model().objects.create_superuser(
            username='sideadmin', email='sideadmin@example.com', password='Str0ngPassw0rd!'
        )
        self.staff = get_user_model().objects.create_user(
            username='sidestaff', password='Str0ngPassw0rd!', is_staff=True
        )

    def test_admin_sidebar_shows_users_without_info_or_reports(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('users:user_list'))
        self.assertNotContains(response, reverse('info:info_list'))
        self.assertNotContains(response, reverse('ofw:report_list'))

    def test_staff_sidebar_hides_users_and_info(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('ofw:profile_list'))
        self.assertContains(response, reverse('ofw:concern_list'))
        self.assertNotContains(response, reverse('users:user_list'))
        self.assertNotContains(response, reverse('info:info_list'))

    def test_staff_sees_staff_role_label(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'Staff')
        self.assertNotContains(response, 'Administrator')



class AuthMessageTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username='msgstaff', password='Str0ngPassw0rd!', is_staff=True
        )

    def test_successful_login_shows_success_message(self):
        response = self.client.post(
            reverse('login'),
            {'username': 'msgstaff', 'password': 'Str0ngPassw0rd!'},
            follow=True,
        )
        self.assertContains(response, 'Logged in successfully.')

    def test_logout_shows_confirmation_and_success_message(self):
        self.client.force_login(self.staff)
        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(
            dashboard, 'Are you sure you want to log out?'
        )

        response = self.client.get(reverse('logout'), follow=True)
        self.assertContains(response, 'Logged out successfully.')
        self.assertContains(response, 'Sign in to start your session')


class PasswordResetTests(TestCase):
    """Password reset works with a real mail backend and in local dev."""

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='resetuser',
            email='reset@example.com',
            password='OldPassw0rd!',
        )

    def _post_email(self, email='reset@example.com'):
        return self.client.post(reverse('password_reset'), {'email': email})

    def test_get_renders_request_form(self):
        response = self.client.get(reverse('password_reset'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Forgot password?')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_existing_email_sends_reset_link(self):
        response = self._post_email()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('reset@example.com', mail.outbox[0].to)
        self.assertIn('/reset/', mail.outbox[0].body)
        # The link is emailed, not rendered on the page.
        self.assertNotContains(response, '/reset/')
        self.assertContains(response, 'Check your email')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend'
    )
    def test_unknown_email_looks_the_same_and_sends_nothing(self):
        response = self._post_email('nobody@example.com')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(mail.outbox), 0)
        self.assertContains(response, 'Check your email')
        self.assertNotContains(response, '/reset/')

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.console.EmailBackend'
    )
    def test_console_backend_shows_link_on_page(self):
        response = self._post_email()

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '/reset/')
        self.assertContains(response, 'Reset your password')

    def test_unusable_password_gets_no_link(self):
        self.user.set_unusable_password()
        self.user.save(update_fields=['password'])

        response = self._post_email()

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, '/reset/')

    def test_reset_link_sets_new_password(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        url = reverse('password_reset_confirm', kwargs={
            'uidb64': uid, 'token': token,
        })

        # Django validates the token on GET and redirects to the "set-password"
        # URL that keeps the token in the session.
        response = self.client.get(url)
        self.assertEqual(response.status_code, 302)
        set_password_url = response.url

        response = self.client.post(set_password_url, {
            'new_password1': 'BrandNewPassw0rd!',
            'new_password2': 'BrandNewPassw0rd!',
        })

        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('BrandNewPassw0rd!'))
