# DataVision Pro - Intelligent Data Analytics Platform

## Overview
A comprehensive intelligent data analytics system built with Streamlit that provides one-click automated data analysis. The system features:
- Automatic data cleaning
- Comprehensive statistical analysis
- Interactive visualizations
- Time period comparisons
- Predictive analytics
- AI-powered chat assistant
- Professional reports with recommendations
- 60-day free trial system with email notifications
- Support contact form

## Project Structure
```
├── app.py                 # Main application (Streamlit)
├── models.py              # Database models (SQLAlchemy) - Users, Subscriptions, Datasets, SupportMessages
├── email_service.py       # Email sending service (Resend integration)
├── data_cleaner.py        # Data cleaning module
├── data_analyzer.py       # Statistical analysis module
├── visualizations.py      # Charts and graphs (Plotly)
├── predictions.py         # Predictions and comparisons
├── ai_assistant.py        # AI module (OpenAI GPT)
├── static/
│   └── logo.png           # Transparent logo (DataVision Pro)
├── .streamlit/
│   └── config.toml        # Streamlit configuration
├── pyproject.toml         # Project dependencies
└── replit.md              # This file
```

## Tech Stack
- **Streamlit**: Interactive web interface
- **Pandas & NumPy**: Data processing and analysis
- **Plotly**: Interactive visualizations
- **Seaborn & Matplotlib**: Additional statistical charts
- **Scikit-learn**: Predictive models
- **SQLAlchemy & PostgreSQL**: Database for users, subscriptions, and historical data
- **OpenAI GPT**: AI for analysis and conversation
- **bcrypt**: Secure password hashing
- **Resend**: Transactional email sending (welcome emails, support notifications)

## Running the App
```bash
streamlit run app.py --server.port 5000
```

## Key Features
1. **File Upload**: Support for CSV and Excel files
2. **Auto Cleaning**: Remove duplicates, handle missing values and outliers. Cleaning runs as an ordered list of toggleable substeps that users can reorder (↑/↓) or extend by inserting custom substeps (Trim Whitespace, Drop Column, Rename Column).
3. **Statistical Analysis**: Descriptive stats, correlations, distributions
4. **Visualizations**: Bar, scatter, box, pie, line charts, heatmaps
5. **Time Tracking**: Save and compare data across time periods
6. **Predictions**: Linear models and trend analysis
7. **ML & Clustering Analytics**: Advanced tab with:
   - Categorical data analysis with pie/bar charts
   - ML prediction models (RandomForest/LinearRegression)
   - K-Means risk clustering with scatter visualizations
   - Enhanced outlier detection with box plots
8. **AI Chat**: Professional chat interface (bottom-aligned input, scrollable history)
9. **AI Reports**: Insights and professional recommendations

## User System
- **Authentication**: Email/password login with bcrypt hashing
- **Registration**: Full name, email, phone, country, gender, specialty (dropdown with Other option)
- **User Roles**: Regular users and Admin
- **Trial System**: 60-day free trial with full Tier 3 access from account creation
- **No guest access**: Account required to use the platform

### Tier System (No Payment - All Free for Testing)
| Feature | Tier 1 | Tier 2 | Tier 3 |
|---------|--------|--------|--------|
| Max File Size | 50 MB | 200 MB | 200 MB |
| Max Rows | 10,000 | 500,000 | 1,000,000 |
| AI Chat | ❌ | ❌ | ✓ |
| Predictions | ❌ | ✓ | ✓ |
| ML & Clustering | ❌ | ✓ | ✓ |
| Export Reports | ❌ | ❌ | ✓ |

### Trial System
- New users get 60-day free trial with Tier 3 (full access)
- Welcome email sent on registration with trial end date
- After trial expires, access is blocked with message to contact for activation
- Users can select any tier freely from the Tiers page

## Email System
- **Provider**: Resend (via Replit connector)
- **Welcome Email**: Sent on registration with trial end date
- **Support Notifications**: Sent to muayad.demaidi.work@gmail.com when users submit support form
- **From Email**: Configured via Resend connector

## Support System
- Contact form at bottom of website (email, name, message)
- Messages saved to database (support_messages table)
- Email notification sent to muayad.demaidi.work@gmail.com

## Admin Panel
Admins can access:
- User management and statistics
- Dataset analytics
- Conversation history
- Platform usage metrics

## Database Schema
- **Users**: Authentication, subscription info, usage stats, phone, country, gender, specialty, trial dates
- **SupportMessages**: Contact form submissions
- **Subscriptions**: Plan details
- **DatasetRecord**: Uploaded files with metadata
- **AnalysisHistory**: Analysis results
- **ChatHistory**: AI conversation logs

## Design
- Theme: "Data Noir" — dark precision aesthetic, deep navy + teal
- Fonts: Syne (headings/display, 800w), DM Sans (body), JetBrains Mono (data/mono)
- CSS variables: --teal #2dd4bf, --bg #07101f, --surface #0c1829, --surface-2 #111f35
- Desktop-first layout: block-container overridden to 1320px max-width
- Glassmorphism cards with border: var(--border) = rgba(45,212,191,0.14)
- Matrix rain background animation (subtle, fixed)
- Landing page: Fixed top navbar (logo + nav links + Sign In), centered hero, single CTA
- Hero H1: 3.75rem Syne 800, gradient teal-to-slate, full desktop width
- Sections: Feature cards (4-col grid), How It Works (3-col), Tiers (3-col with dividers)
- Professional support section: 2-column (info left, form right) inside rounded card
- Footer: 3-column grid (brand desc / Platform links / Support links) + copyright bar
- Dashboard: Sidebar with logo, navigation, user badge

## User Preferences
- Language: Arabic (Levantine dialect) for communication
- No payment integration - all tiers freely accessible
- Professional, sophisticated design aesthetic
- Column types displayed in English

## History
- **January 2026**: Initial release with full features
- **January 2026**: UI redesign with neon theme, user authentication, subscription system, admin panel, English interface
- **February 2026**: Converted to 3-tier system without payment, Matrix theme with glassmorphism
- **February 2026**: Major redesign - removed sidebar from home, professional registration form, 60-day trial system, email notifications, support contact form, require account for all access
