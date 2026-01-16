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

## Project Structure
```
├── app.py                 # Main application (Streamlit)
├── models.py              # Database models (SQLAlchemy) - Users, Subscriptions, Datasets
├── data_cleaner.py        # Data cleaning module
├── data_analyzer.py       # Statistical analysis module
├── visualizations.py      # Charts and graphs (Plotly)
├── predictions.py         # Predictions and comparisons
├── ai_assistant.py        # AI module (OpenAI GPT)
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

## Running the App
```bash
streamlit run app.py --server.port 5000
```

## Key Features
1. **File Upload**: Support for CSV and Excel files
2. **Auto Cleaning**: Remove duplicates, handle missing values and outliers
3. **Statistical Analysis**: Descriptive stats, correlations, distributions
4. **Visualizations**: Bar, scatter, box, pie, line charts, heatmaps
5. **Time Tracking**: Save and compare data across time periods
6. **Predictions**: Linear models and trend analysis
7. **AI Chat**: Ask any question about your data
8. **AI Reports**: Insights and professional recommendations

## User System
- **Authentication**: Email/password login with bcrypt hashing
- **User Roles**: Regular users and Admin
- **Subscriptions**: Free and Premium tiers

### Subscription Tiers
| Feature | Free | Premium ($29/mo) |
|---------|------|------------------|
| Max Rows | 1,000 | Unlimited |
| Analyses/Day | 5 | Unlimited |
| File Size | 5 MB | 100 MB |
| AI Chat | ❌ | ✓ |
| Predictions | ❌ | ✓ |
| Export Reports | ❌ | ✓ |

## Admin Panel
Admins can access:
- User management and statistics
- Dataset analytics
- Conversation history
- Platform usage metrics

## Database Schema
- **Users**: Authentication, subscription info, usage stats
- **Subscriptions**: Plan details, Stripe integration (future)
- **DatasetRecord**: Uploaded files with metadata
- **AnalysisHistory**: Analysis results
- **ChatHistory**: AI conversation logs

## Design
- Theme: Neon purple/pink with dark background
- Animated floating data background
- Professional, modern UI
- Responsive layout

## Notes
- **Stripe Integration**: User dismissed Stripe connector. For payment processing, manually add STRIPE_SECRET_KEY as a secret when ready to enable payments.

## History
- **January 2026**: Initial release with full features
- **January 2026**: UI redesign with neon theme, user authentication, subscription system, admin panel, English interface
