def ai_analyze_text(text):
    # Simulated AI analysis
    if 'prix fixe' in text or '3-course' in text:
        return {
            'has_prix_fixe': True,
            'confidence': 0.8,
            'summary': 'Detected possible prix fixe menu based on keywords.'
        }
    return {
        'has_prix_fixe': False,
        'confidence': 0.2,
        'summary': 'No clear evidence of prix fixe menu detected.'
    }