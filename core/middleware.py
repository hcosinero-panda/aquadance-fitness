"""
Custom middleware for Aquadance fitness app
"""
from django.shortcuts import redirect
from django.urls import reverse


class AdminSuperuserOnlyMiddleware:
    """
    Middleware to restrict /admin/ access to superusers only.
    Redirects non-superusers to staff-portal.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Check if accessing /admin/
        if request.path.startswith('/admin/'):
            # Allow login/logout
            if request.path in ['/admin/login/', '/admin/logout/']:
                pass
            # For any other /admin/ path, require superuser
            elif request.user.is_authenticated:
                if not request.user.is_superuser:
                    return redirect('dashboard')  # Redirect to staff-portal
            # If not authenticated, Django admin will handle login redirect

        response = self.get_response(request)
        return response
