"""
Mock data fallback for demo mode when API calls are unavailable.

Provides realistic-looking sample provider data so the app can demonstrate
its scoring and ranking logic without live API access.
"""

MOCK_PROVIDERS = [
    {
        "place_id": "mock_001",
        "name": "Sunrise Integrative Health Center",
        "address": "1234 Wellness Blvd, Austin, TX 78701",
        "lat": 30.2672,
        "lng": -97.7431,
        "types": ["health", "doctor", "point_of_interest", "establishment"],
        "rating": 4.7,
        "review_count": 89,
        "phone": "(512) 555-0101",
        "website": "https://example.com/sunrise-integrative",
        "hours": "Mon-Fri: 8:00 AM - 6:00 PM; Sat: 9:00 AM - 1:00 PM",
        "review_texts": [
            "Great integrative approach to chronic pain management. Dr. Chen combines acupuncture with conventional medicine.",
            "Helped me reduce my reliance on pain medication through a holistic treatment plan.",
            "The team here takes a whole-person approach. They helped with my digestive issues and stress.",
        ],
    },
    {
        "place_id": "mock_002",
        "name": "Dr. Sarah Mitchell, MD - Family Medicine",
        "address": "567 Main St, Austin, TX 78702",
        "lat": 30.2600,
        "lng": -97.7200,
        "types": ["doctor", "health", "point_of_interest", "establishment"],
        "rating": 4.5,
        "review_count": 156,
        "phone": "(512) 555-0102",
        "website": "https://example.com/dr-mitchell",
        "hours": "Mon-Fri: 7:30 AM - 5:00 PM",
        "review_texts": [
            "Dr. Mitchell is thorough and listens to concerns. She referred me to a great specialist for my GI issues.",
            "Excellent primary care doctor. She takes time to explain treatment options.",
            "Good at coordinating care across multiple specialists.",
        ],
    },
    {
        "place_id": "mock_003",
        "name": "Austin Physical Therapy & Rehab",
        "address": "890 Recovery Lane, Austin, TX 78703",
        "lat": 30.2800,
        "lng": -97.7500,
        "types": ["physiotherapist", "health", "point_of_interest", "establishment"],
        "rating": 4.8,
        "review_count": 203,
        "phone": "(512) 555-0103",
        "website": "https://example.com/austin-pt",
        "hours": "Mon-Fri: 6:00 AM - 7:00 PM; Sat: 8:00 AM - 12:00 PM",
        "review_texts": [
            "After knee surgery, they got me walking pain-free in 8 weeks. Highly recommend.",
            "The therapists here focus on long-term recovery, not just quick fixes.",
            "They offer telehealth consultations for follow-up appointments which is very convenient.",
        ],
    },
    {
        "place_id": "mock_004",
        "name": "Harmony Acupuncture & Wellness",
        "address": "345 Zen Way, Austin, TX 78704",
        "lat": 30.2450,
        "lng": -97.7600,
        "types": ["health", "point_of_interest", "establishment"],
        "rating": 4.9,
        "review_count": 67,
        "phone": "(512) 555-0104",
        "website": None,
        "hours": "Tue-Sat: 10:00 AM - 6:00 PM",
        "review_texts": [
            "Acupuncture sessions here significantly reduced my anxiety and chronic back pain.",
            "A calming environment with skilled practitioners. My inflammation improved noticeably.",
        ],
    },
    {
        "place_id": "mock_005",
        "name": "Capital Gastroenterology Associates",
        "address": "678 Medical Pkwy, Austin, TX 78705",
        "lat": 30.2950,
        "lng": -97.7350,
        "types": ["doctor", "health", "point_of_interest", "establishment"],
        "rating": 4.3,
        "review_count": 112,
        "phone": "(512) 555-0105",
        "website": "https://example.com/capital-gastro",
        "hours": "Mon-Fri: 8:00 AM - 5:00 PM",
        "review_texts": [
            "Finally got a proper diagnosis for my digestive problems after years of searching.",
            "The doctors here are specialists in GI disorders. Thorough testing and clear explanations.",
        ],
    },
    {
        "place_id": "mock_006",
        "name": "Balanced Body Chiropractic",
        "address": "901 Spine St, Austin, TX 78731",
        "lat": 30.3200,
        "lng": -97.7500,
        "types": ["chiropractor", "health", "point_of_interest", "establishment"],
        "rating": 4.6,
        "review_count": 78,
        "phone": "(512) 555-0106",
        "website": "https://example.com/balanced-body",
        "hours": "Mon-Fri: 9:00 AM - 6:00 PM; Sat: 9:00 AM - 2:00 PM",
        "review_texts": [
            "Great adjustments and they also do soft tissue work. My back pain is much better.",
            "Non-invasive approach to pain management. They also offer nutritional counseling.",
        ],
    },
    {
        "place_id": "mock_007",
        "name": "Nourish Nutrition Counseling",
        "address": "234 Health Ave, Austin, TX 78745",
        "lat": 30.2100,
        "lng": -97.7700,
        "types": ["health", "point_of_interest", "establishment"],
        "rating": 4.4,
        "review_count": 34,
        "phone": None,
        "website": "https://example.com/nourish",
        "hours": "Mon-Thu: 9:00 AM - 5:00 PM",
        "review_texts": [
            "The registered dietitian here helped me identify food triggers for my GI problems.",
            "Virtual appointments available which is great for busy schedules.",
        ],
    },
    {
        "place_id": "mock_008",
        "name": "Serenity Massage & Bodywork",
        "address": "456 Calm Circle, Austin, TX 78746",
        "lat": 30.2700,
        "lng": -97.8000,
        "types": ["spa", "health", "point_of_interest", "establishment"],
        "rating": 4.7,
        "review_count": 145,
        "phone": "(512) 555-0108",
        "website": "https://example.com/serenity-massage",
        "hours": "Mon-Sun: 9:00 AM - 9:00 PM",
        "review_texts": [
            "Therapeutic massage that really helps with muscle tension and stress relief.",
            "I go here for chronic pain management. Much better than just taking pills.",
        ],
    },
    {
        "place_id": "mock_009",
        "name": "Lone Star Pain Management Clinic",
        "address": "789 Medical Center Dr, Austin, TX 78756",
        "lat": 30.3100,
        "lng": -97.7400,
        "types": ["doctor", "health", "point_of_interest", "establishment"],
        "rating": 4.1,
        "review_count": 92,
        "phone": "(512) 555-0109",
        "website": "https://example.com/lonestar-pain",
        "hours": "Mon-Fri: 8:00 AM - 5:00 PM",
        "review_texts": [
            "Comprehensive pain management with multiple treatment options including non-opioid approaches.",
            "They create individualized plans. Mine includes PT referrals and nerve blocks.",
        ],
    },
    {
        "place_id": "mock_010",
        "name": "Nature's Path Naturopathic Clinic",
        "address": "321 Green Way, Austin, TX 78757",
        "lat": 30.3300,
        "lng": -97.7300,
        "types": ["health", "point_of_interest", "establishment"],
        "rating": 4.5,
        "review_count": 41,
        "phone": "(512) 555-0110",
        "website": "https://example.com/natures-path",
        "hours": "Mon-Fri: 9:00 AM - 5:00 PM",
        "review_texts": [
            "Naturopathic approach that complemented my conventional treatment well.",
            "They focus on root causes of fatigue and inflammation rather than just symptoms.",
        ],
    },
]

# Mock NPI results for providers that would be NPI-eligible
MOCK_NPI_RESULTS = {
    "mock_002": {
        "status": "NPI matched",
        "npi_number": "1234567890",
        "npi_name": "Sarah Mitchell",
        "taxonomy": "Family Medicine",
        "confidence": 0.9,
    },
    "mock_003": {
        "status": "possible NPI match",
        "npi_number": "2345678901",
        "npi_name": "Austin Physical Therapy",
        "taxonomy": "Physical Therapist",
        "confidence": 0.5,
    },
    "mock_005": {
        "status": "NPI matched",
        "npi_number": "3456789012",
        "npi_name": "Capital Gastroenterology Associates",
        "taxonomy": "Gastroenterology",
        "confidence": 0.9,
    },
    "mock_009": {
        "status": "possible NPI match",
        "npi_number": "4567890123",
        "npi_name": "Lone Star Pain Management",
        "taxonomy": "Pain Medicine",
        "confidence": 0.5,
    },
}

# Mock ZIP code coordinates
MOCK_ZIP_COORDS = {
    "78701": (30.2672, -97.7431),
    "78702": (30.2634, -97.7186),
    "78703": (30.2880, -97.7610),
    "78704": (30.2410, -97.7614),
    "78705": (30.2950, -97.7420),
    "10001": (40.7484, -73.9967),
    "90210": (34.0901, -118.4065),
    "60601": (41.8819, -87.6278),
}


def get_mock_zip_coords(zip_code: str) -> tuple[float, float] | None:
    """Return mock coordinates for a ZIP code, defaulting to Austin center."""
    return MOCK_ZIP_COORDS.get(zip_code.strip(), (30.2672, -97.7431))


def get_mock_npi_result(place_id: str) -> dict:
    """Return mock NPI result for a place, or default no-match."""
    return MOCK_NPI_RESULTS.get(place_id, {
        "status": "no API match available",
        "npi_number": None,
        "npi_name": None,
        "taxonomy": None,
        "confidence": 0.0,
    })
