from django.contrib import admin
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from core import views

urlpatterns = [
    # Django Admin (owner-only) - Replace custom admin-dashboard
    path('admin/', admin.site.urls),
    
    # Custom Staff/Student Portal Frontend Routes
    path('', views.login_view, name='login'),                  # Root URL goes straight to Login
    path('login/', views.login_view, name='login_redirect'),   # Alternative /login/ route
    path('logout/', views.logout_view, name='logout'),
    path('staff-portal/', views.dashboard_view, name='dashboard'),
    path('expiration-alerts/', views.expiration_alerts_view, name='expiration_alerts'),
    path('check-in/', views.checkin_page_view, name='checkin'),
    path('membership-cards/', views.membership_cards_view, name='membership_cards'),
    path('api/scan/', views.scan_qr_api, name='scan_qr_api'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Customize admin site
admin.site.site_header = "Aquafit Management System"
admin.site.site_title = "Aquafit Admin"
admin.site.index_title = "Admin Dashboard"