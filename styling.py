import streamlit as st


def last_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700&display=swap');

        html, body, [class*="css"] {
            font-family: 'Poppins', sans-serif;
        }

        .stApp {
            background: linear-gradient(135deg, #0E1117 0%, #1A1D29 50%, #12141C 100%);
        }

        h1 {
            background: linear-gradient(90deg, #7C5CFC, #5CC8FC);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 700 !important;
        }

        h2 {
            font-weight: 600 !important;
            border-left: 4px solid #7C5CFC;
            padding-left: 12px;
            margin-top: 2rem !important;
        }

        [data-testid="stMetric"] {
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-radius: 16px;
            padding: 18px 14px;
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
        }

        [data-testid="stMetric"]:hover {
            transform: translateY(-4px);
            box-shadow: 0 8px 24px rgba(124, 92, 252, 0.3);
            border-color: rgba(124, 92, 252, 0.5);
            background: rgba(255, 255, 255, 0.1);
        }

        [data-testid="stMetricLabel"] {
            font-weight: 400 !important;
            opacity: 0.7;
        }

        [data-testid="stMetricValue"] {
            font-weight: 700 !important;
            font-size: 1.6rem !important;
        }

        hr {
            border-color: rgba(255, 255, 255, 0.1) !important;
        }

        [data-testid="stCaptionContainer"] {
            opacity: 0.6;
        }

        .stVegaLiteChart, [data-testid="stArrowVegaLiteChart"] {
            background: rgba(255, 255, 255, 0.03);
            border-radius: 16px;
            padding: 8px;
        }
                
                .event-kort {
            display: flex;
            align-items: center;
            gap: 16px;
            background: rgba(255, 255, 255, 0.08);
            border: 1px solid rgba(255, 255, 255, 0.15);
            border-left: 4px solid #7C5CFC;
            border-radius: 12px;
            padding: 14px 18px;
            margin-bottom: 10px;
            backdrop-filter: blur(10px);
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }

        .event-kort:hover {
            transform: translateX(4px);
            box-shadow: 0 4px 16px rgba(124, 92, 252, 0.25);
        }

        .event-tid {
            font-weight: 700;
            font-size: 1rem;
            color: #7C5CFC;
            min-width: 60px;
        }

        .event-navn {
            font-weight: 400;
            font-size: 1rem;
            opacity: 0.9;
        }
        </style>
    """, unsafe_allow_html=True)