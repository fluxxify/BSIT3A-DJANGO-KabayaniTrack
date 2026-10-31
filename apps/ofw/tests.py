import os
import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.ofw.forms import CheckInForm
from apps.ofw.hotlines import (
    COUNTRY_HOTLINES,
    PHILIPPINE_HOTLINES,
    automatic_local_hotlines,
)
from apps.ofw.locations import COUNTRY_ALIASES, COUNTRY_CHOICES, canonical_country
from apps.ofw.models import (
    CheckIn,
    Concern,
    ConcernProof,
    EmergencyContact,
    MonitoringReport,
    Notification,
    OFWProfile,
    SafeLocation,
)
from apps.ofw.roles import mark_as_ofw

User = get_user_model()

TEMP_MEDIA_DIR = tempfile.mkdtemp(prefix='kabayani_test_media_')


class OFWCrudTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='officer', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.user)
        self.ofw = OFWProfile.objects.create(
            user=self.user,
            first_name='Juan',
            last_name='Dela Cruz',
            country='Saudi Arabia',
            employer_name='ACME Corp',
        )

    def test_list_pages_render(self):
        for name in ['profile_list', 'assessment_list', 'checkin_list',
                     'concern_list', 'contact_list', 'report_list']:
            with self.subTest(name=name):
                response = self.client.get(reverse(f'ofw:{name}'))
                self.assertEqual(response.status_code, 200)

    def test_dashboard_renders(self):
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Registered OFWs')

    def test_create_profile_via_ajax(self):
        response = self.client.post(reverse('ofw:profile_save_ajax'), {
            'first_name': 'Maria',
            'last_name': 'Santos',
            'country': 'Qatar',
            'welfare_status': 'active',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(OFWProfile.objects.filter(first_name='Maria', user=self.user).exists())

    def test_create_checkin_via_ajax(self):
        response = self.client.post(reverse('ofw:checkin_save_ajax'), {
            'ofw': self.ofw.pk,
            'checkin_date': '2026-10-01T10:30',
            'method': 'call',
            'condition': 'safe',
            'contact_person': 'Ate Joy',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CheckIn.objects.count(), 1)
        self.assertEqual(CheckIn.objects.get().contact_person, 'Ate Joy')

    def test_save_rejects_invalid_data(self):
        response = self.client.post(reverse('ofw:profile_save_ajax'), {
            'first_name': '',
            'last_name': '',
            'country': '',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())

    def test_get_ajax_returns_record(self):
        response = self.client.get(reverse('ofw:profile_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['first_name'], 'Juan')

    def test_delete_ajax(self):
        response = self.client.post(reverse('ofw:profile_delete_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.json()['status'], 'deleted')
        self.assertFalse(OFWProfile.objects.filter(pk=self.ofw.pk).exists())

    def test_other_user_cannot_access_record(self):
        other = User.objects.create_user(username='other', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:profile_get_ajax', args=[self.ofw.pk]))
        self.assertEqual(response.status_code, 404)

    def test_create_emergency_contact_via_ajax(self):
        response = self.client.post(reverse('ofw:contact_save_ajax'), {
            'name': 'Philippine Embassy — Riyadh',
            'contact_type': 'embassy',
            'country': 'Saudi Arabia',
            'city': 'Riyadh',
            'phone': '+966 11 488 8001',
            'email': 'riyadh.pe@dfa.gov.ph',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'success')
        self.assertTrue(
            EmergencyContact.objects.filter(name='Philippine Embassy — Riyadh', user=self.user).exists()
        )

    def test_contact_requires_phone(self):
        response = self.client.post(reverse('ofw:contact_save_ajax'), {
            'name': 'No Number',
            'contact_type': 'other',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('error', response.json())


class OFWPortalTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ofw1', password='Passw0rd!23')
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Ana', last_name='Reyes', country='Dubai',
        )
        self.client.force_login(self.user)

    def test_portal_home_renders(self):
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/portal/home.html')

    def test_portal_pages_render(self):
        for name in ['portal', 'portal_profile', 'portal_checkins',
                     'portal_concerns', 'portal_contacts']:
            with self.subTest(name=name):
                response = self.client.get(reverse(f'ofw:{name}'))
                self.assertEqual(response.status_code, 200)

    def test_profile_page_has_country_and_city_choices(self):
        response = self.client.get(reverse('ofw:portal_profile'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="country-options"')
        self.assertContains(response, 'id="city-options"')
        self.assertContains(response, 'list="country-options"')
        self.assertContains(response, 'list="city-options"')
        self.assertContains(response, 'Saudi Arabia')

        cities = self.client.get(reverse('ofw:portal_cities'), {'country': 'Kuwait'})
        self.assertEqual(cities.status_code, 200)
        self.assertIn('Kuwait City', cities.json()['cities'])

    def test_profile_accepts_country_outside_choices(self):
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'country': 'Somewhereland',
            'city_abroad': 'Imaginary City',
            'email': 'ana@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.country, 'Somewhereland')
        self.assertEqual(self.profile.city_abroad, 'Imaginary City')

    def test_profile_update_saves_to_own_profile(self):
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Ana',
            'last_name': 'Reyes',
            'country': 'Dubai',
            'email': 'ana@example.com',
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.email, 'ana@example.com')
        self.assertEqual(self.profile.user, self.user)

    def test_self_checkin_created_and_linked(self):
        response = self.client.post(reverse('ofw:portal_checkins'), {
            'method': 'call',
            'condition': 'safe',
            'contact_person': 'Kuya Ben',
            'notes': 'Doing well',
        })
        self.assertEqual(response.status_code, 302)
        checkin = CheckIn.objects.get(ofw=self.profile, user=self.user)
        self.assertEqual(checkin.notes, 'Doing well')
        self.assertEqual(checkin.contact_person, 'Kuya Ben')

    def test_self_concern_created_and_linked(self):
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'salary',
            'severity': 'high',
            'description': 'Two months unpaid',
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.filter(ofw=self.profile, user=self.user).first()
        self.assertIsNotNone(concern)
        self.assertEqual(concern.title, 'Two months unpaid')
        self.assertEqual(concern.status, Concern.Status.OPEN)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
class OFWProfilePictureTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='ofwphoto', password='Passw0rd!23'
        )
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Mila', last_name='Santos', country='Kuwait',
        )
        self.client.force_login(self.user)

    def test_profile_picture_upload_and_display(self):
        picture = SimpleUploadedFile('me.jpg', b'\xff\xd8\xff fakejpg', 'image/jpeg')
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Mila',
            'last_name': 'Santos',
            'country': 'Kuwait',
            'email': 'mila@example.com',
            'profile_picture': picture,
        })
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertTrue(
            self.profile.profile_picture.name.startswith('ofw/profile_pictures/')
        )
        page = self.client.get(reverse('ofw:portal_profile'))
        self.assertContains(page, self.profile.profile_picture.url)

    def test_profile_picture_rejects_non_image(self):
        picture = SimpleUploadedFile('cv.txt', b'not an image', 'text/plain')
        response = self.client.post(reverse('ofw:portal_profile'), {
            'first_name': 'Mila',
            'last_name': 'Santos',
            'country': 'Kuwait',
            'profile_picture': picture,
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Upload a JPG, PNG, WEBP or GIF image.')
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.profile_picture)

    def test_profile_list_shows_profile_picture(self):
        self.profile.profile_picture.save(
            'me.jpg',
            SimpleUploadedFile('me.jpg', b'\xff\xd8\xff fakejpg', 'image/jpeg'),
        )
        response = self.client.get(reverse('ofw:profile_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.profile.profile_picture.url)
        self.assertContains(response, 'avatar avatar-sm rounded-circle')


@override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
class ConcernProofUploadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='ofwproof', password='Passw0rd!23')
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Lia', last_name='Cruz', country='Hong Kong',
        )
        self.client.force_login(self.user)

    def test_concern_with_photo_and_video_proof(self):
        photo = SimpleUploadedFile('proof.jpg', b'\xff\xd8\xff fakejpg', 'image/jpeg')
        video = SimpleUploadedFile('proof.mp4', b'\x00\x00\x00 fakemp4', 'video/mp4')
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'abuse',
            'severity': 'critical',
            'description': 'Physically harmed at work',
            'proof_files': [photo, video],
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.get(ofw=self.profile, description='Physically harmed at work')
        self.assertEqual(concern.title, 'Physically harmed at work')
        proofs = concern.proofs.all()
        self.assertEqual(proofs.count(), 2)
        self.assertTrue(any(p.is_image for p in proofs))
        self.assertTrue(any(p.is_video for p in proofs))
        for p in proofs:
            self.assertTrue(p.file.name.startswith('concern_proofs/'))
            self.assertTrue(p.file.storage.exists(p.file.name))

    def test_rejects_disallowed_file_type(self):
        bad = SimpleUploadedFile('notes.exe', b'MZ binary', 'application/octet-stream')
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'other',
            'severity': 'low',
            'description': 'Agency asked for payment',
            'proof_files': [bad],
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'not an accepted file type')
        self.assertFalse(
            Concern.objects.filter(description='Agency asked for payment').exists()
        )

    def test_concern_without_proof_still_works(self):
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'health',
            'severity': 'medium',
            'description': 'Just text',
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.get(ofw=self.profile)
        self.assertEqual(concern.title, 'Just text')
        self.assertEqual(concern.proofs.count(), 0)

    def test_concern_without_description_uses_category_as_title(self):
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'health',
            'severity': 'low',
            'description': '',
        })
        self.assertEqual(response.status_code, 302)
        concern = Concern.objects.get(ofw=self.profile)
        self.assertEqual(concern.title, 'Health / Medical concern')

    def test_portal_page_renders_with_proof_field(self):
        response = self.client.get(reverse('ofw:portal_concerns'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'enctype="multipart/form-data"')
        self.assertContains(response, 'name="proof_files"')
        self.assertContains(response, 'id="concern-camera-btn"')
        self.assertContains(response, 'id="concern-gallery-btn"')
        self.assertContains(response, 'id="concern-camera-input"')
        self.assertContains(response, 'capture="environment"')
        self.assertContains(response, 'id="concernCameraModal"')
        self.assertContains(response, 'id="concern-camera-video"')
        self.assertContains(response, 'id="concern-camera-shutter"')
        self.assertContains(response, 'id="concern-camera-record"')
        self.assertContains(response, 'id="concern-camera-timer"')
        self.assertContains(response, 'Record Video')
        self.assertContains(response, 'id="concern-proof-preview"')
        self.assertNotContains(response, 'name="title"')

    def test_management_detail_shows_proofs(self):
        concern = Concern.objects.create(
            ofw=self.profile, user=self.user, title='Abuse case',
            category='abuse', severity='high', status='open',
            reported_date=timezone.localdate(), description='Hurt by employer',
        )
        ConcernProof.objects.create(
            concern=concern,
            file=SimpleUploadedFile('evidence.png', b'\x89PNG fakepng', 'image/png'),
            original_name='evidence.png',
        )
        staff = User.objects.create_user(
            username='mgrproof', password='Passw0rd!23', is_staff=True
        )
        concern.user = staff
        concern.save(update_fields=['user'])
        self.client.force_login(staff)
        response = self.client.get(reverse('ofw:concern_detail', args=[concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Photo / Video Proof')
        self.assertContains(response, 'evidence.png')

    def test_management_user_redirected_from_portal(self):
        staff = User.objects.create_user(
            username='mgr', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_admin_sees_ofw_submission_in_console(self):
        self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'documents',
            'severity': 'critical',
            'description': 'Employer took my passport',
        })
        admin = User.objects.create_superuser(
            username='root', email='root@example.com', password='Passw0rd!23'
        )
        self.client.force_login(admin)
        response = self.client.get(reverse('ofw:concern_list'))
        self.assertContains(response, 'Employer took my passport')

    def test_admin_form_lists_ofw_owned_profiles(self):
        admin = User.objects.create_superuser(
            username='root2', email='root2@example.com', password='Passw0rd!23'
        )
        form = CheckInForm(user=admin)
        self.assertIn(self.profile, form.fields['ofw'].queryset)

    def test_admin_can_create_checkin_for_ofw_owned_profile(self):
        admin = User.objects.create_superuser(
            username='root3', email='root3@example.com', password='Passw0rd!23'
        )
        self.client.force_login(admin)
        response = self.client.post(reverse('ofw:checkin_save_ajax'), {
            'ofw': self.profile.pk,
            'checkin_date': '2026-10-01T10:30',
            'method': 'call',
            'condition': 'safe',
            'contact_person': 'Kuya Ben',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(CheckIn.objects.get().contact_person, 'Kuya Ben')


@override_settings(MEDIA_ROOT=TEMP_MEDIA_DIR)
class RecordCleanupTests(TestCase):
    """Deleting records must also remove their files and stale notifications."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='cleanup_ofw', password='Passw0rd!23'
        )
        self.staff = User.objects.create_user(
            username='cleanup_staff', password='Passw0rd!23', is_staff=True
        )
        self.profile = OFWProfile.objects.create(
            user=self.user,
            first_name='Cleanup',
            last_name='Test',
            country='Qatar',
        )

    def test_deleting_concern_removes_proof_files_and_notifications(self):
        concern = Concern.objects.create(
            ofw=self.profile,
            user=self.user,
            title='Concern with proof',
            category='other',
            severity='low',
            status='open',
            reported_date=timezone.localdate(),
        )
        proof = ConcernProof.objects.create(
            concern=concern,
            file=SimpleUploadedFile('proof.png', b'\x89PNG fakepng', 'image/png'),
            original_name='proof.png',
        )
        notification = Notification.objects.create(
            recipient=self.staff,
            title='New concern',
            url=reverse('ofw:concern_detail', args=[concern.pk]),
        )
        proof_path = proof.file.path
        self.assertTrue(os.path.exists(proof_path))

        concern.delete()

        self.assertFalse(os.path.exists(proof_path))
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def test_deleting_checkin_removes_notifications(self):
        checkin = CheckIn.objects.create(
            ofw=self.profile,
            user=self.user,
            checkin_date=timezone.now(),
            method=CheckIn.Method.APP,
            condition=CheckIn.Condition.SAFE,
        )
        notification = Notification.objects.create(
            recipient=self.staff,
            title='New check-in',
            url=reverse('ofw:checkin_detail', args=[checkin.pk]),
        )

        checkin.delete()

        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def test_deleting_profile_removes_picture_and_notifications(self):
        self.profile.profile_picture.save(
            'profile.png',
            SimpleUploadedFile('profile.png', b'\x89PNG fakepng', 'image/png'),
        )
        picture_path = self.profile.profile_picture.path
        notification = Notification.objects.create(
            recipient=self.staff,
            title='New OFW',
            url=reverse('ofw:profile_detail', args=[self.profile.pk]),
        )
        self.assertTrue(os.path.exists(picture_path))

        self.profile.delete()

        self.assertFalse(os.path.exists(picture_path))
        self.assertFalse(Notification.objects.filter(pk=notification.pk).exists())

    def test_replacing_profile_picture_removes_old_file(self):
        self.profile.profile_picture.save(
            'old.png',
            SimpleUploadedFile('old.png', b'\x89PNG oldpng', 'image/png'),
        )
        old_path = self.profile.profile_picture.path
        self.assertTrue(os.path.exists(old_path))

        self.profile.profile_picture.save(
            'new.png',
            SimpleUploadedFile('new.png', b'\x89PNG newpng', 'image/png'),
        )
        new_path = self.profile.profile_picture.path

        self.assertFalse(os.path.exists(old_path))
        self.assertTrue(os.path.exists(new_path))

    def test_deleting_report_removes_attachment(self):
        report = MonitoringReport.objects.create(
            user=self.user,
            title='Monthly report',
            period_start=timezone.localdate(),
            period_end=timezone.localdate(),
            attachment=SimpleUploadedFile('report.pdf', b'%PDF fake', 'application/pdf'),
        )
        attachment_path = report.attachment.path
        self.assertTrue(os.path.exists(attachment_path))

        report.delete()

        self.assertFalse(os.path.exists(attachment_path))


class StaffFullAccessTests(TestCase):
    """Staff accounts (non-superuser) see every OFW record, like an admin."""

    def setUp(self):
        self.staff = User.objects.create_user(
            username='stafffull', password='Passw0rd!23', is_staff=True
        )
        self.ofw_user = User.objects.create_user(
            username='ofwfull', password='Passw0rd!23'
        )
        self.profile = OFWProfile.objects.create(
            user=self.ofw_user, first_name='Nena', last_name='Diaz', country='Qatar',
        )
        self.concern = Concern.objects.create(
            ofw=self.profile, user=self.ofw_user, title='Withheld wages',
            category='salary', severity='high', status='open',
            reported_date=timezone.localdate(),
        )

    def test_staff_can_open_another_users_profile(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:profile_detail', args=[self.profile.pk]))
        self.assertEqual(response.status_code, 200)

    def test_staff_can_open_another_users_concern(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Withheld wages')

    def test_staff_list_ajax_includes_other_users_records(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:concern_list_ajax'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Withheld wages')

    def test_staff_form_queryset_lists_all_ofws(self):
        form = CheckInForm(user=self.staff)
        self.assertIn(self.profile, form.fields['ofw'].queryset)

    def test_staff_redirected_away_from_ofw_portal(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:portal'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


class DashboardDrilldownTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer2', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.at_risk = OFWProfile.objects.create(
            user=self.staff, first_name='Risky', last_name='One',
            country='Kuwait', welfare_status='distressed',
        )
        self.safe = OFWProfile.objects.create(
            user=self.staff, first_name='Calm', last_name='Two',
            country='Japan', welfare_status='active',
        )
        Concern.objects.create(
            ofw=self.at_risk, user=self.staff, title='Open case',
            category='salary', severity='high', status='open',
            reported_date='2026-10-01',
        )
        Concern.objects.create(
            ofw=self.safe, user=self.staff, title='Closed case',
            category='other', severity='low', status='closed',
            reported_date='2026-09-01',
        )

    def test_dashboard_shows_drilldown_links(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, reverse('ofw:profile_list'))
        self.assertContains(response, reverse('ofw:checkin_list'))
        self.assertContains(response, reverse('ofw:concern_list'))
        self.assertContains(response, reverse('ofw:contact_list'))
        self.assertNotContains(response, reverse('ofw:report_list'))

    def test_welfare_status_filter_limits_results(self):
        response = self.client.get(
            reverse('ofw:profile_list'),
            {'welfare_status': 'distressed,needs_support'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risky')
        self.assertNotContains(response, 'Calm')
        self.assertContains(response, 'Filtered view')

    def test_dashboard_deployment_map_lists_countries(self):
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'OFW Deployment Map')
        self.assertContains(response, 'Assignments by Country')
        self.assertContains(response, 'Kuwait')
        self.assertContains(response, 'Japan')
        self.assertContains(
            response, reverse('ofw:profile_list') + '?country=Kuwait'
        )
        self.assertContains(response, 'deployment-map')

    def test_dashboard_map_data_is_valid_json(self):
        import json
        import re

        response = self.client.get(reverse('dashboard'))
        html = response.content.decode()
        regions = json.loads(re.search(r'var regions = (.*?);', html).group(1))
        ofws = json.loads(re.search(r'var ofws = (.*?);', html).group(1))
        self.assertEqual(regions['KW'], 1)
        kuwait = [o for o in ofws if o['country'] == 'Kuwait']
        self.assertTrue(kuwait)
        self.assertEqual(
            kuwait[0]['link'],
            reverse('ofw:profile_detail', args=[self.at_risk.pk]),
        )
        self.assertEqual(kuwait[0]['iso2'], 'KW')

    def test_country_filter_limits_results(self):
        response = self.client.get(
            reverse('ofw:profile_list'), {'country': 'Kuwait'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risky')
        self.assertNotContains(response, 'Calm')

    def test_country_filter_is_case_insensitive(self):
        response = self.client.get(
            reverse('ofw:profile_list'), {'country': 'kuwait'}
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Risky')
        self.assertNotContains(response, 'Calm')

    def test_concern_status_filter_limits_results(self):
        response = self.client.get(
            reverse('ofw:concern_list'),
            {'status': 'open,in_progress,escalated'},
        )
        self.assertContains(response, 'Open case')
        self.assertNotContains(response, 'Closed case')

    def test_search_preserves_filter(self):
        response = self.client.get(
            reverse('ofw:profile_list'),
            {'welfare_status': 'distressed', 'q': 'Risky'},
        )
        self.assertContains(response, 'name="welfare_status"')


class CheckInDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer3', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.profile = OFWProfile.objects.create(
            user=self.staff, first_name='Nora', last_name='Cruz', country='Qatar',
        )
        self.checkin = CheckIn.objects.create(
            ofw=self.profile, user=self.staff, checkin_date=timezone.now(),
            method='call', condition='safe', contact_person='Kuya Ben (manager)',
            notes='Checked in by phone; doing well and in good spirits.',
        )

    def test_detail_page_renders(self):
        response = self.client.get(reverse('ofw:checkin_detail', args=[self.checkin.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/checkin_detail.html')
        self.assertContains(response, 'Nora')
        self.assertContains(response, 'Checked in by phone')
        self.assertContains(response, 'Kuya Ben (manager)')

    def test_list_shows_view_action(self):
        response = self.client.get(reverse('ofw:checkin_list'))
        self.assertContains(
            response,
            reverse('ofw:checkin_detail', args=[self.checkin.pk]),
        )

    def test_other_user_cannot_view_detail(self):
        other = User.objects.create_user(username='other2', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:checkin_detail', args=[self.checkin.pk]))
        self.assertEqual(response.status_code, 404)


class ConcernDetailTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='officer4', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(self.staff)
        self.profile = OFWProfile.objects.create(
            user=self.staff, first_name='Rina', last_name='Lopez', country='Kuwait',
        )
        self.concern = Concern.objects.create(
            ofw=self.profile, user=self.staff, title='Unpaid overtime',
            category='salary', severity='high', status='open',
            reported_date=timezone.localdate(),
            description='Overtime hours were not paid for the last three months.',
        )

    def test_detail_page_renders(self):
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/concern_detail.html')
        self.assertContains(response, 'Unpaid overtime')
        self.assertContains(response, 'Overtime hours were not paid')

    def test_list_shows_view_action(self):
        response = self.client.get(reverse('ofw:concern_list'))
        self.assertContains(
            response,
            reverse('ofw:concern_detail', args=[self.concern.pk]),
        )

    def test_other_user_cannot_view_detail(self):
        other = User.objects.create_user(username='other3', password='Passw0rd!23')
        self.client.force_login(other)
        response = self.client.get(reverse('ofw:concern_detail', args=[self.concern.pk]))
        self.assertEqual(response.status_code, 404)


class EmergencyContactActionTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username='root4', email='root4@example.com', password='Passw0rd!23'
        )
        self.client.force_login(self.admin)
        self.owwa = EmergencyContact.objects.create(
            name='OWWA Hotline', contact_type='owwa', country='Philippines',
            phone='+63 2 8551 1545', email='owwa@owwa.gov.ph',
        )
        self.custom = EmergencyContact.objects.create(
            name='Partner Site', contact_type='other', phone='09171234567',
            website='https://example.com',
        )
        self.hospital = EmergencyContact.objects.create(
            name='City Clinic', contact_type='hospital', phone='09179999999',
        )

    def test_website_url_fallbacks(self):
        self.assertEqual(self.custom.website_url(), 'https://example.com')
        self.assertEqual(self.owwa.website_url(), 'https://owwa.gov.ph')
        self.assertEqual(self.hospital.website_url(), '')

    def test_list_shows_call_and_website_actions(self):
        response = self.client.get(reverse('ofw:contact_list'))
        self.assertContains(response, 'tel:+63285511545')
        self.assertContains(response, 'https://owwa.gov.ph')
        self.assertContains(response, 'https://example.com')

    def test_list_hides_website_action_for_type_without_site(self):
        response = self.client.get(
            reverse('ofw:contact_list'), {'contact_type': 'hospital'}
        )
        self.assertNotContains(response, 'Open Website')
        self.assertNotContains(response, 'fa-globe')

    def test_list_can_open_website_in_new_tab(self):
        response = self.client.get(reverse('ofw:contact_list'))
        self.assertContains(response, 'target="_blank"')

    def test_portal_contacts_shows_call_and_website_actions(self):
        ofw = User.objects.create_user(username='ofw_contact', password='Passw0rd!23')
        mark_as_ofw(ofw)
        EmergencyContact.objects.create(
            name='OWWA Hotline', contact_type='owwa', country='Philippines',
            phone='+63 2 8551 1545', user=None,
        )
        self.client.force_login(ofw)
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'tel:+63285511545')
        self.assertContains(response, 'https://owwa.gov.ph')


class CountryHotlineDataTests(SimpleTestCase):
    """Bundled data must cover every country in the profile datalist."""

    def test_every_country_has_a_fallback_number(self):
        missing = [
            country for country in COUNTRY_CHOICES
            if not COUNTRY_HOTLINES.get(country)
        ]
        self.assertEqual(missing, [])

        for country, entries in COUNTRY_HOTLINES.items():
            with self.subTest(country=country):
                self.assertTrue(entries)
                numbers = [entry['phone'] for entry in entries]
                self.assertEqual(len(numbers), len(set(numbers)))
                valid_types = {
                    choice[0] for choice in EmergencyContact.ContactType.choices
                }
                for entry in entries:
                    self.assertTrue(entry['name'].strip())
                    self.assertTrue(entry['phone'].strip())
                    self.assertIn(entry['contact_type'], valid_types)

    def test_philippine_numbers_are_bundled(self):
        phones = {row['phone'] for row in PHILIPPINE_HOTLINES}
        self.assertIn('911', phones)
        self.assertIn('1348', phones)
        self.assertIn('+63 2 8551 1545', phones)

    def test_country_aliases_resolve(self):
        self.assertEqual(canonical_country('UAE'), 'United Arab Emirates')
        self.assertEqual(canonical_country('u.a.e.'), 'United Arab Emirates')
        self.assertEqual(canonical_country('KSA'), 'Saudi Arabia')
        self.assertEqual(canonical_country('qatar'), 'Qatar')

    def test_aliases_point_to_known_countries(self):
        unknown = {
            alias: country
            for alias, country in COUNTRY_ALIASES.items()
            if country not in COUNTRY_CHOICES
        }
        self.assertEqual(unknown, {})
        for country in COUNTRY_CHOICES:
            self.assertEqual(canonical_country(country), country)

    def test_philippines_is_not_duplicated_in_local_list(self):
        self.assertEqual(automatic_local_hotlines('Philippines'), [])


class LocationHotlineTests(TestCase):
    """The portal shows hotlines automatically for the OFW's deployment country."""

    def setUp(self):
        self.ofw = User.objects.create_user(
            username='hotline_ofw', password='Passw0rd!23'
        )
        mark_as_ofw(self.ofw)
        self.profile = OFWProfile.objects.create(
            user=self.ofw, first_name='Ana', last_name='Cruz',
            country='Qatar', city_abroad='Doha',
        )
        EmergencyContact.objects.create(
            name='Philippine Embassy — Doha', contact_type='embassy',
            country='Qatar', city='Doha', phone='+974 4400 0000', user=None,
        )
        EmergencyContact.objects.create(
            name='POLO Doha', contact_type='polo',
            country='Qatar', city='Doha', phone='+974 4400 1111', user=None,
        )
        EmergencyContact.objects.create(
            name='DMW Action Center', contact_type='dmw',
            country='Philippines', city='Mandaluyong', phone='1348', user=None,
        )
        EmergencyContact.objects.create(
            name='Hong Kong Consulate', contact_type='embassy',
            country='Hong Kong', city='Central', phone='+852 2823 8500', user=None,
        )
        self.client.force_login(self.ofw)

    def test_location_hotlines_shown_automatically(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Hotlines for Qatar')
        self.assertContains(response, 'Philippine Embassy — Doha')
        self.assertContains(response, 'POLO Doha')

    def test_static_local_emergency_number_shown(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Qatar emergency hotline')
        self.assertContains(response, 'tel:999')
        self.assertContains(response, 'Police, fire, and medical emergencies.')

    def test_national_hotline_always_shown(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'National Hotlines')
        self.assertContains(response, 'DMW Action Center')

    def test_philippine_hotlines_are_automatic(self):
        EmergencyContact.objects.filter(country='Philippines').delete()
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Philippines National Emergency Hotline')
        self.assertContains(response, 'OWWA 24/7 Hotline')
        self.assertContains(response, 'Philippine Red Cross')
        self.assertContains(response, 'tel:911')

    def test_other_country_hotline_not_shown(self):
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertNotContains(response, 'Hong Kong Consulate')
        self.assertNotContains(response, 'Japan police')

    def test_country_alias_uses_canonical_hotlines(self):
        self.profile.country = 'UAE'
        self.profile.save(update_fields=['country'])
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Hotlines for United Arab Emirates')
        self.assertContains(response, 'United Arab Emirates police')

    def test_philippines_uses_national_hotlines_without_empty_local_card(self):
        self.profile.country = 'Philippines'
        self.profile.city_abroad = 'Manila'
        self.profile.save(update_fields=['country', 'city_abroad'])
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Philippines National Emergency Hotline')
        self.assertNotContains(response, 'Hotlines for Philippines')
        self.assertNotContains(response, 'No hotlines are on file for')

    def test_blank_country_still_shows_philippine_hotlines(self):
        self.profile.country = ''
        self.profile.save(update_fields=['country'])
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Philippines National Emergency Hotline')
        self.assertContains(response, 'Set your')
        self.assertNotContains(response, 'Hotlines for Qatar')

    def test_personal_family_contact_hidden_from_hotlines(self):
        other = User.objects.create_user(username='other_ofw', password='Passw0rd!23')
        mark_as_ofw(other)
        EmergencyContact.objects.create(
            name='Other Family Member', contact_type='family',
            country='Qatar', phone='+63 917 000 0000',
            user=other,
        )
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertNotContains(response, 'Other Family Member')


class FamilyContactTests(TestCase):
    """OFWs add, edit and remove their own family emergency contacts directly."""

    def setUp(self):
        self.ofw = User.objects.create_user(
            username='req_ofw', password='Passw0rd!23'
        )
        mark_as_ofw(self.ofw)
        self.profile = OFWProfile.objects.create(
            user=self.ofw, first_name='Rico', last_name='Bautista', country='Kuwait',
        )

    def _add_contact(self):
        self.client.force_login(self.ofw)
        return self.client.post(reverse('ofw:portal_contacts'), {
            'name': 'Liza Bautista',
            'relationship': 'Spouse',
            'phone': '+63 917 555 1234',
            'email': '',
            'address': '10 Rizal St., Cebu City',
            'notes': '',
        })

    def test_ofw_adds_family_contact_directly(self):
        response = self._add_contact()
        self.assertEqual(response.status_code, 302)
        contact = EmergencyContact.objects.get(user=self.ofw)
        self.assertEqual(contact.contact_type, 'family')
        self.assertEqual(contact.name, 'Liza Bautista')
        self.assertEqual(contact.relationship, 'Spouse')
        self.assertEqual(contact.phone, '+63 917 555 1234')

    def test_added_contact_appears_in_portal(self):
        self._add_contact()
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Liza Bautista')
        self.assertContains(response, 'Spouse')

    def test_ofw_can_edit_own_contact(self):
        self._add_contact()
        contact = EmergencyContact.objects.get(user=self.ofw)
        response = self.client.post(
            reverse('ofw:portal_contact_edit', args=[contact.pk]),
            {
                'name': 'Liza Bautista-Santos',
                'relationship': 'Spouse',
                'phone': '+63 917 555 9999',
                'email': 'liza@example.com',
                'address': '10 Rizal St., Cebu City',
                'notes': '',
            },
        )
        self.assertEqual(response.status_code, 302)
        contact.refresh_from_db()
        self.assertEqual(contact.name, 'Liza Bautista-Santos')
        self.assertEqual(contact.phone, '+63 917 555 9999')

    def test_ofw_can_delete_own_contact(self):
        self._add_contact()
        contact = EmergencyContact.objects.get(user=self.ofw)
        response = self.client.post(
            reverse('ofw:portal_contact_delete', args=[contact.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmergencyContact.objects.filter(user=self.ofw).exists())

    def test_delete_requires_post(self):
        self._add_contact()
        contact = EmergencyContact.objects.get(user=self.ofw)
        self.client.get(reverse('ofw:portal_contact_delete', args=[contact.pk]))
        self.assertTrue(EmergencyContact.objects.filter(pk=contact.pk).exists())

    def test_owned_public_hotline_not_listed_as_family_contact(self):
        EmergencyContact.objects.create(
            user=self.ofw, name='OWWA Hotline', phone='1348',
            contact_type=EmergencyContact.ContactType.OWWA, country='Philippines',
        )
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('ofw:portal_contacts'))
        body = response.content.decode()
        family_section = body[body.find('My Family Emergency Contacts'):]
        self.assertNotIn('OWWA Hotline', family_section)

    def test_ofw_can_delete_non_family_personal_contact(self):
        employer = EmergencyContact.objects.create(
            user=self.ofw, name='Al Noor Construction HR', phone='+966 11 000 0000',
            contact_type='employer',
        )
        self.client.force_login(self.ofw)
        response = self.client.post(
            reverse('ofw:portal_contact_delete', args=[employer.pk]),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(EmergencyContact.objects.filter(pk=employer.pk).exists())

    def test_ofw_cannot_edit_or_delete_others_contact(self):
        other = User.objects.create_user(username='other_ofw', password='Passw0rd!23')
        mark_as_ofw(other)
        other_contact = EmergencyContact.objects.create(
            user=other, name='Other Contact', contact_type='family', phone='09171112222',
        )
        self.client.force_login(self.ofw)
        edit = self.client.get(
            reverse('ofw:portal_contact_edit', args=[other_contact.pk])
        )
        self.assertEqual(edit.status_code, 404)
        delete = self.client.post(
            reverse('ofw:portal_contact_delete', args=[other_contact.pk])
        )
        self.assertEqual(delete.status_code, 404)
        self.assertTrue(EmergencyContact.objects.filter(pk=other_contact.pk).exists())

    def test_contact_form_renders(self):
        self.client.force_login(self.ofw)
        response = self.client.get(reverse('ofw:portal_contacts'))
        self.assertContains(response, 'Add a Family Emergency Contact')
        self.assertNotContains(response, 'Request a Family Emergency Contact')


class EmergencySosTests(TestCase):
    """The one-tap SOS page and the Call / WhatsApp / Viber deep links."""

    def setUp(self):
        self.ofw = User.objects.create_user(username='sos_ofw', password='Passw0rd!23')
        mark_as_ofw(self.ofw)
        self.profile = OFWProfile.objects.create(
            user=self.ofw, first_name='Nico', last_name='Cruz', country='United Arab Emirates',
        )
        self.client.force_login(self.ofw)

    def test_sos_page_renders(self):
        response = self.client.get(reverse('ofw:portal_sos'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'ofw/portal/sos.html')
        self.assertContains(response, 'In an emergency, call right away')

    def test_portal_home_links_to_sos(self):
        response = self.client.get(reverse('ofw:portal'))
        self.assertContains(response, reverse('ofw:portal_sos'))

    def test_sos_lists_local_and_national_hotlines(self):
        EmergencyContact.objects.create(
            user=self.ofw, name='Philippine Embassy — Abu Dhabi', phone='+971 2 419 2000',
            contact_type='embassy', country='United Arab Emirates',
        )
        EmergencyContact.objects.create(
            user=self.ofw, name='OWWA Hotline', phone='1348',
            contact_type='owwa', country='Philippines',
        )
        response = self.client.get(reverse('ofw:portal_sos'))
        self.assertContains(response, 'Philippine Embassy — Abu Dhabi')
        self.assertContains(response, 'OWWA Hotline')

    def test_dial_and_messaging_links_are_clean(self):
        contact = EmergencyContact.objects.create(
            user=self.ofw, name='Mama', phone='+63 917 555 1234',
            contact_type='family',
        )
        self.assertEqual(contact.dial_number, '+639175551234')
        self.assertEqual(contact.whatsapp_url, 'https://wa.me/639175551234')
        self.assertEqual(contact.viber_url, 'viber://chat?number=%2B639175551234')

        response = self.client.get(reverse('ofw:portal_sos'))
        self.assertContains(response, 'tel:+639175551234')
        self.assertContains(response, 'https://wa.me/639175551234')
        self.assertContains(response, 'viber://chat?number=%2B639175551234')

    def test_sos_includes_static_local_and_philippine_hotlines(self):
        response = self.client.get(reverse('ofw:portal_sos'))
        self.assertContains(response, 'United Arab Emirates police')
        self.assertContains(response, 'tel:999')
        self.assertContains(response, 'Philippine Red Cross')

    def test_sos_requires_ofw_account(self):
        staff = User.objects.create_user(
            username='sos_staff', password='Passw0rd!23', is_staff=True
        )
        self.client.force_login(staff)
        response = self.client.get(reverse('ofw:portal_sos'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))


class NotificationTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(
            username='notif_staff', password='Passw0rd!23', is_staff=True
        )
        self.ofw_user = User.objects.create_user(
            username='notif_ofw', password='Passw0rd!23'
        )
        self.profile = OFWProfile.objects.create(
            user=self.ofw_user,
            first_name='Liza',
            last_name='Cruz',
            country='Qatar',
        )

    def test_ofw_concern_notifies_managers(self):
        self.client.force_login(self.ofw_user)
        response = self.client.post(reverse('ofw:portal_concerns'), {
            'category': 'salary',
            'severity': 'high',
            'description': 'No overtime pay for two months',
        })
        self.assertEqual(response.status_code, 302)

        notification = Notification.objects.filter(recipient=self.staff).first()
        self.assertIsNotNone(notification)
        self.assertIn('New concern from Liza Cruz', notification.title)
        self.assertEqual(notification.level, Notification.Level.DANGER)
        concern = Concern.objects.get(description='No overtime pay for two months')
        self.assertEqual(notification.url, reverse('ofw:concern_detail', args=[concern.pk]))

    def test_ofw_checkin_notifies_managers(self):
        self.client.force_login(self.ofw_user)
        response = self.client.post(reverse('ofw:portal_checkins'), {
            'method': 'call',
            'condition': 'needs_assistance',
            'contact_person': 'Ate Grace',
            'notes': 'Need help',
        })
        self.assertEqual(response.status_code, 302)

        notification = Notification.objects.filter(recipient=self.staff).first()
        self.assertIsNotNone(notification)
        self.assertIn('New check-in from Liza Cruz', notification.title)
        self.assertIn('Ate Grace', notification.message)
        self.assertEqual(notification.level, Notification.Level.WARNING)

    def test_management_checkin_notifies_ofw_with_contact(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('ofw:checkin_save_ajax'), {
            'ofw': self.profile.pk,
            'checkin_date': '2026-10-01T10:30',
            'method': 'call',
            'condition': 'safe',
            'contact_person': 'Ate Grace',
            'notes': 'Reached by phone',
        })
        self.assertEqual(response.status_code, 200)

        notification = Notification.objects.filter(recipient=self.ofw_user).first()
        self.assertIsNotNone(notification)
        self.assertIn('Management logged a check-in', notification.message)
        self.assertIn('Ate Grace', notification.message)
        self.assertEqual(notification.level, Notification.Level.SUCCESS)

    def test_management_concern_status_change_notifies_ofw(self):
        self.client.force_login(self.staff)
        create = self.client.post(reverse('ofw:concern_save_ajax'), {
            'ofw': self.profile.pk,
            'title': 'Passport withheld',
            'category': 'documents',
            'severity': 'high',
            'status': 'open',
            'reported_date': timezone.localdate().isoformat(),
        })
        self.assertEqual(create.status_code, 200)
        concern = Concern.objects.get(title='Passport withheld')
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.ofw_user, title='Concern recorded'
            ).exists()
        )

        update = self.client.post(reverse('ofw:concern_save_ajax'), {
            'id': concern.pk,
            'ofw': self.profile.pk,
            'title': 'Passport withheld',
            'category': 'documents',
            'severity': 'high',
            'status': 'resolved',
            'reported_date': concern.reported_date.isoformat(),
        })
        self.assertEqual(update.status_code, 200)
        notification = Notification.objects.filter(
            recipient=self.ofw_user, title='Concern status updated'
        ).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.level, Notification.Level.SUCCESS)
        self.assertIn('Resolved', notification.message)

    def test_management_assessment_notifies_ofw(self):
        self.client.force_login(self.staff)
        response = self.client.post(reverse('ofw:assessment_save_ajax'), {
            'ofw': self.profile.pk,
            'status': 'needs_support',
            'risk_level': 'medium',
            'assessment_date': timezone.localdate().isoformat(),
            'assessor': 'Case officer',
        })
        self.assertEqual(response.status_code, 200)
        notification = Notification.objects.filter(recipient=self.ofw_user).first()
        self.assertIsNotNone(notification)
        self.assertEqual(notification.title, 'New welfare assessment')
        self.assertEqual(notification.level, Notification.Level.WARNING)

    def test_notifications_page_only_lists_own_notifications(self):
        Notification.objects.create(
            recipient=self.staff, title='Staff alert', message='For staff only',
        )
        Notification.objects.create(
            recipient=self.ofw_user, title='OFW alert', message='For OFW only',
        )
        self.client.force_login(self.staff)
        response = self.client.get(reverse('ofw:notifications'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Staff alert')
        self.assertNotContains(response, 'OFW alert')
        self.assertContains(response, 'title="View notification"')
        self.assertEqual(response.context['unread_count'], 1)

    def test_notification_open_marks_read_and_redirects(self):
        notification = Notification.objects.create(
            recipient=self.staff, title='Open me', url='/home/',
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('ofw:notification_open', args=[notification.pk])
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/home/')
        notification.refresh_from_db()
        self.assertTrue(notification.is_read)

    def test_notification_open_rejects_other_users(self):
        notification = Notification.objects.create(
            recipient=self.ofw_user, title='Private', url='/home/',
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('ofw:notification_open', args=[notification.pk])
        )
        self.assertEqual(response.status_code, 404)

    def test_mark_all_notifications_read(self):
        Notification.objects.create(recipient=self.staff, title='One')
        Notification.objects.create(recipient=self.staff, title='Two')
        self.client.force_login(self.staff)
        response = self.client.post(reverse('ofw:notifications_mark_all_read'))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(
            Notification.objects.filter(recipient=self.staff, is_read=False).exists()
        )

    def test_bell_shows_unread_count(self):
        Notification.objects.create(recipient=self.staff, title='Unread alert')
        self.client.force_login(self.staff)
        response = self.client.get(reverse('dashboard'))
        self.assertContains(response, 'dh-notif-badge')
        self.assertContains(response, 'Unread alert')

    def test_management_opening_concern_notifies_ofw_once(self):
        concern = Concern.objects.create(
            ofw=self.profile,
            user=self.ofw_user,
            title='Withheld wages',
            category='salary',
            severity='high',
            status='open',
            reported_date=timezone.localdate(),
        )
        self.client.force_login(self.staff)
        url = reverse('ofw:concern_detail', args=[concern.pk])

        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        concern.refresh_from_db()
        self.assertIsNotNone(concern.read_by_management_at)

        notifications = Notification.objects.filter(
            recipient=self.ofw_user, title='Your concern has been read'
        )
        self.assertEqual(notifications.count(), 1)
        self.assertIn('has been read by the management', notifications.first().message)
        self.assertEqual(notifications.first().url, reverse('ofw:portal_concerns'))

        self.client.get(url)
        self.assertEqual(notifications.count(), 1)

    def test_ofw_opening_own_concern_does_not_mark_it_read(self):
        concern = Concern.objects.create(
            ofw=self.profile,
            user=self.ofw_user,
            title='My own concern',
            category='other',
            severity='low',
            status='open',
            reported_date=timezone.localdate(),
        )
        self.client.force_login(self.ofw_user)
        response = self.client.get(reverse('ofw:concern_detail', args=[concern.pk]))
        self.assertEqual(response.status_code, 200)
        concern.refresh_from_db()
        self.assertIsNone(concern.read_by_management_at)
        self.assertFalse(
            Notification.objects.filter(
                recipient=self.ofw_user, title='Your concern has been read'
            ).exists()
        )

    def test_management_opening_concern_editor_notifies_ofw(self):
        concern = Concern.objects.create(
            ofw=self.profile,
            user=self.ofw_user,
            title='Editor test concern',
            category='other',
            severity='medium',
            status='open',
            reported_date=timezone.localdate(),
        )
        self.client.force_login(self.staff)
        response = self.client.get(
            reverse('ofw:concern_get_ajax', args=[concern.pk])
        )
        self.assertEqual(response.status_code, 200)
        concern.refresh_from_db()
        self.assertIsNotNone(concern.read_by_management_at)
        self.assertTrue(
            Notification.objects.filter(
                recipient=self.ofw_user, title='Your concern has been read'
            ).exists()
        )

class SafeLocationNearbyTests(TestCase):
    """Safe places are location-aware for OFWs and fall back to PH data."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='safespot', password='Passw0rd!23'
        )
        mark_as_ofw(self.user)
        self.profile = OFWProfile.objects.create(
            user=self.user, first_name='Mila', last_name='Reyes',
            country='Saudi Arabia', city_abroad='Riyadh',
        )
        self.ph_location = SafeLocation.objects.create(
            name='Philippine General Hospital',
            location_type=SafeLocation.LocationType.HOSPITAL,
            country='Philippines', city='Manila',
            address='Taft Avenue', phone='',
            latitude='14.578600', longitude='120.985700',
        )
        self.client.force_login(self.user)

    def test_ofw_sees_near_me_page_with_all_active_locations(self):
        response = self.client.get(reverse('ofw:safe_locations'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Safe Places Near Me')
        self.assertContains(response, 'id="useMyLocationBtn"')
        self.assertContains(response, 'class="col-sm-6 col-lg-4 loc-card"')
        self.assertContains(response, 'Philippine General Hospital')
        self.assertNotContains(response, 'Add Safe Location')

    def test_near_me_page_hides_inactive_locations(self):
        SafeLocation.objects.create(
            name='Closed Police Post',
            location_type=SafeLocation.LocationType.POLICE_STATION,
            country='Philippines', is_active=False,
        )
        response = self.client.get(reverse('ofw:safe_locations'))
        self.assertNotContains(response, 'Closed Police Post')

    def test_emergency_sos_falls_back_to_philippines(self):
        response = self.client.get(reverse('ofw:portal_emergency_sos'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Philippine General Hospital')
        self.assertContains(response, 'id="nearbyLocateBtn"')
        self.assertContains(response, 'id="nearbyMap"')

    def test_emergency_sos_prefers_profile_country(self):
        SafeLocation.objects.create(
            name='Riyadh Central Police Station',
            location_type=SafeLocation.LocationType.POLICE_STATION,
            country='Saudi Arabia', city='Riyadh',
            latitude='24.713600', longitude='46.675300',
        )
        response = self.client.get(reverse('ofw:portal_emergency_sos'))
        self.assertContains(response, 'Riyadh Central Police Station')
        self.assertNotContains(response, 'Philippine General Hospital')


class SeedSafeLocationsCommandTests(TestCase):
    def test_command_seeds_philippine_locations_idempotently(self):
        from django.core.management import call_command

        call_command('seed_safe_locations', verbosity=0)
        first_count = SafeLocation.objects.filter(
            country='Philippines', is_active=True
        ).count()
        self.assertGreaterEqual(first_count, 30)
        self.assertTrue(
            SafeLocation.objects.filter(
                name='Philippine General Hospital',
                latitude__isnull=False,
                longitude__isnull=False,
            ).exists()
        )

        call_command('seed_safe_locations', verbosity=0)
        second_count = SafeLocation.objects.filter(
            country='Philippines', is_active=True
        ).count()
        self.assertEqual(first_count, second_count)
