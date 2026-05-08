import os
import requests
import resend


def get_resend_credentials():
    # First, check for standard environment variables for production
    env_api_key = os.environ.get("RESEND_API_KEY")
    env_from_email = os.environ.get("RESEND_FROM_EMAIL", "onboarding@resend.dev")
    if env_api_key:
        return env_api_key, env_from_email

    # Fallback to Replit-specific logic for development/replit deployments
    hostname = os.environ.get("REPLIT_CONNECTORS_HOSTNAME")
    
    x_replit_token = None
    if os.environ.get("REPL_IDENTITY"):
        x_replit_token = "repl " + os.environ["REPL_IDENTITY"]
    elif os.environ.get("WEB_REPL_RENEWAL"):
        x_replit_token = "depl " + os.environ["WEB_REPL_RENEWAL"]
    
    if not x_replit_token or not hostname:
        return None, None
    
    try:
        resp = requests.get(
            f"https://{hostname}/api/v2/connection?include_secrets=true&connector_names=resend",
            headers={
                "Accept": "application/json",
                "X_REPLIT_TOKEN": x_replit_token
            },
            timeout=10
        )
        data = resp.json()
        connection = data.get("items", [None])[0]
        if connection and connection.get("settings"):
            api_key = connection["settings"].get("api_key")
            from_email = connection["settings"].get("from_email", "onboarding@resend.dev")
            return api_key, from_email
    except Exception as e:
        print(f"Error getting Resend credentials: {e}")
    
    return None, None


def send_welcome_email(user_email, user_name, trial_end_date):
    api_key, from_email = get_resend_credentials()
    
    if not api_key:
        print("Resend API key not available, skipping email")
        return False
    
    resend.api_key = api_key
    
    trial_end_str = trial_end_date.strftime("%B %d, %Y") if trial_end_date else "N/A"
    
    html_content = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f172a; color: #e2e8f0; padding: 2rem; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #14b8a6; font-size: 2rem; margin: 0;">AXIOM</h1>
            <p style="color: #94a3b8; margin-top: 0.5rem;">Welcome to the Future of Data Analytics</p>
        </div>
        
        <div style="background: rgba(20, 184, 166, 0.1); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h2 style="color: #e2e8f0; margin-top: 0;">Hello {user_name}! 👋</h2>
            <p>Thank you for joining AXIOM. Your account has been created successfully and your <strong style="color: #14b8a6;">60-day free trial</strong> has started!</p>
        </div>
        
        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h3 style="color: #14b8a6; margin-top: 0;">📅 Trial Details</h3>
            <p><strong>Trial End Date:</strong> <span style="color: #14b8a6;">{trial_end_str}</span></p>
            <p style="color: #94a3b8;">After your trial ends, you'll need to contact our team for activation to continue using the platform.</p>
        </div>
        
        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h3 style="color: #14b8a6; margin-top: 0;">🚀 What You Can Do</h3>
            <ul style="color: #cbd5e1; line-height: 1.8;">
                <li>Upload CSV & Excel files for instant analysis</li>
                <li>Auto-clean your data with one click</li>
                <li>Generate interactive visualizations</li>
                <li>Get AI-powered insights and recommendations</li>
                <li>Build predictive models</li>
                <li>Export professional reports</li>
            </ul>
        </div>
        
        <div style="text-align: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(148, 163, 184, 0.2);">
            <p style="color: #94a3b8; font-size: 0.9rem;">Need help? Contact us at:</p>
            <p style="color: #14b8a6;">muayad.demaidi.work@gmail.com</p>
        </div>
    </div>
    """
    
    try:
        params = {
            "from": from_email,
            "to": [user_email],
            "subject": "Welcome to AXIOM - Your 60-Day Free Trial Has Started!",
            "html": html_content
        }
        
        email_response = resend.Emails.send(params)
        print(f"Welcome email sent to {user_email}: {email_response}")
        return True
    except Exception as e:
        print(f"Error sending welcome email: {e}")
        return False


def send_password_reset_email(user_email, user_name, reset_url):
    """Send a password-reset email styled to match the welcome email."""
    api_key, from_email = get_resend_credentials()

    if not api_key:
        print("Resend API key not available, skipping password reset email")
        return False

    resend.api_key = api_key

    safe_name = user_name or "there"

    html_content = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f172a; color: #e2e8f0; padding: 2rem; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #14b8a6; font-size: 2rem; margin: 0;">AXIOM</h1>
            <p style="color: #94a3b8; margin-top: 0.5rem;">Password Reset Request</p>
        </div>

        <div style="background: rgba(20, 184, 166, 0.1); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h2 style="color: #e2e8f0; margin-top: 0;">Hi {safe_name},</h2>
            <p style="color: #cbd5e1; line-height: 1.7;">We received a request to reset the password for your AXIOM account. Click the button below to choose a new password. This link is valid for <strong style="color: #14b8a6;">1 hour</strong> and can be used only once.</p>
        </div>

        <div style="text-align: center; margin: 2rem 0;">
            <a href="{reset_url}" style="display: inline-block; background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 100%); color: #07101f; text-decoration: none; font-family: 'DM Sans', Arial, sans-serif; font-weight: 700; font-size: 1rem; padding: 0.95rem 2.25rem; border-radius: 10px; box-shadow: 0 8px 24px rgba(45,212,191,0.28);">Reset Password</a>
        </div>

        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem;">
            <p style="color: #94a3b8; font-size: 0.85rem; margin: 0 0 0.5rem 0;">If the button above doesn't work, copy and paste this link into your browser:</p>
            <p style="color: #14b8a6; font-size: 0.85rem; word-break: break-all; margin: 0;">{reset_url}</p>
        </div>

        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem;">
            <p style="color: #cbd5e1; font-size: 0.9rem; line-height: 1.6; margin: 0;">If you did not request a password reset, you can safely ignore this email — your current password will remain unchanged.</p>
        </div>

        <div style="text-align: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(148, 163, 184, 0.2);">
            <p style="color: #94a3b8; font-size: 0.9rem;">Need help? Contact us at:</p>
            <p style="color: #14b8a6;">muayad.demaidi.work@gmail.com</p>
        </div>
    </div>
    """

    text_content = (
        f"Hi {safe_name},\n\n"
        "We received a request to reset the password for your AXIOM "
        "account. Open the link below to choose a new password. This link is "
        "valid for 1 hour and can be used only once.\n\n"
        f"{reset_url}\n\n"
        "If you did not request a password reset, you can safely ignore this email."
    )

    try:
        params = {
            "from": from_email,
            "to": [user_email],
            "subject": "Reset your AXIOM password",
            "html": html_content,
            "text": text_content,
        }

        email_response = resend.Emails.send(params)
        print(f"Password reset email sent to {user_email}: {email_response}")
        return True
    except Exception as e:
        print(f"Error sending password reset email: {e}")
        return False


def send_password_changed_email(user_email, user_name):
    """Send a confirmation email after a password change, styled to match the welcome email."""
    api_key, from_email = get_resend_credentials()

    if not api_key:
        print("Resend API key not available, skipping password changed email")
        return False

    resend.api_key = api_key

    safe_name = user_name or "there"
    support_email = "muayad.demaidi.work@gmail.com"
    support_subject = "Unrecognized password change on my AXIOM account"
    support_link = (
        f"mailto:{support_email}"
        f"?subject={support_subject.replace(' ', '%20')}"
    )

    html_content = f"""
    <div style="font-family: 'Inter', Arial, sans-serif; max-width: 600px; margin: 0 auto; background: #0f172a; color: #e2e8f0; padding: 2rem; border-radius: 12px;">
        <div style="text-align: center; margin-bottom: 2rem;">
            <h1 style="color: #14b8a6; font-size: 2rem; margin: 0;">AXIOM</h1>
            <p style="color: #94a3b8; margin-top: 0.5rem;">Password Changed</p>
        </div>

        <div style="background: rgba(20, 184, 166, 0.1); border: 1px solid rgba(20, 184, 166, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h2 style="color: #e2e8f0; margin-top: 0;">Hi {safe_name},</h2>
            <p style="color: #cbd5e1; line-height: 1.7;">Your AXIOM password was just changed. If you made this change, no further action is needed.</p>
        </div>

        <div style="background: rgba(15, 23, 42, 0.8); border: 1px solid rgba(148, 163, 184, 0.2); border-radius: 8px; padding: 1.5rem; margin-bottom: 1.5rem;">
            <h3 style="color: #14b8a6; margin-top: 0;">Wasn't you?</h3>
            <p style="color: #cbd5e1; line-height: 1.7; margin-bottom: 1.25rem;">If you did <strong>not</strong> change your password, your account may be at risk. Please contact our support team right away so we can help secure it.</p>
            <div style="text-align: center;">
                <a href="{support_link}" style="display: inline-block; background: linear-gradient(135deg, #2dd4bf 0%, #14b8a6 100%); color: #07101f; text-decoration: none; font-family: 'DM Sans', Arial, sans-serif; font-weight: 700; font-size: 1rem; padding: 0.85rem 2rem; border-radius: 10px; box-shadow: 0 8px 24px rgba(45,212,191,0.28);">Wasn't me — contact support</a>
            </div>
        </div>

        <div style="text-align: center; margin-top: 2rem; padding-top: 1.5rem; border-top: 1px solid rgba(148, 163, 184, 0.2);">
            <p style="color: #94a3b8; font-size: 0.9rem;">Need help? Contact us at:</p>
            <p style="color: #14b8a6;">{support_email}</p>
        </div>
    </div>
    """

    text_content = (
        f"Hi {safe_name},\n\n"
        "Your AXIOM password was just changed. If you made this "
        "change, no further action is needed.\n\n"
        "If this wasn't you, please contact our support team right away so we "
        f"can help secure your account: {support_email}\n"
    )

    try:
        params = {
            "from": from_email,
            "to": [user_email],
            "subject": "Your AXIOM password was just changed",
            "html": html_content,
            "text": text_content,
        }

        email_response = resend.Emails.send(params)
        print(f"Password changed email sent to {user_email}: {email_response}")
        return True
    except Exception as e:
        print(f"Error sending password changed email: {e}")
        return False


def send_support_notification(user_email, user_name, message):
    api_key, from_email = get_resend_credentials()
    
    if not api_key:
        print("Resend API key not available, skipping support email")
        return False
    
    resend.api_key = api_key

    # Escape user-controlled fields before interpolating into HTML/subject
    # so a malicious sender cannot inject arbitrary markup, links, or
    # script-bearing tags into the support inbox.
    import html as _html
    safe_name = _html.escape(user_name or "N/A")
    safe_email = _html.escape(user_email or "")
    safe_message_html = _html.escape(message or "").replace("\n", "<br>")
    safe_subject_label = _html.escape(user_name or user_email or "anonymous")

    html_content = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 2rem;">
        <h2 style="color: #0d9488;">New Support Message - AXIOM</h2>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.5rem; margin-bottom: 1rem;">
            <p><strong>From:</strong> {safe_name}</p>
            <p><strong>Email:</strong> {safe_email}</p>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 8px; padding: 1.5rem;">
            <h3>Message:</h3>
            <p>{safe_message_html}</p>
        </div>
    </div>
    """
    
    try:
        params = {
            "from": from_email,
            "to": ["muayad.demaidi.work@gmail.com"],
            "subject": f"Support Request from {safe_subject_label} - AXIOM",
            "html": html_content
        }
        
        email_response = resend.Emails.send(params)
        print(f"Support notification sent: {email_response}")
        return True
    except Exception as e:
        print(f"Error sending support notification: {e}")
        return False
