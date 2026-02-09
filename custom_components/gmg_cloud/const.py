"""Constants for the GMG Cloud integration."""

DOMAIN = "gmg_cloud"

# AWS Cognito Configuration (extracted from GMG Prime APK)
COGNITO_USER_POOL_ID = "us-east-1_i4HRNwzTt"
COGNITO_CLIENT_ID = "2me003sbd4ouslkekf2uco2cna"
COGNITO_REGION = "us-east-1"

# GMG API
API_BASE_URL = "https://prime-api.gmgserver.net/v1"

# TCP Server for real-time communication
TCP_SERVER = "remote.gmgserver.net"
TCP_PORT = 8061

# Polling intervals (seconds)
SCAN_INTERVAL = 30  # default / fallback
SCAN_INTERVAL_ACTIVE = 2  # when grill is on (grillState > 0)
SCAN_INTERVAL_IDLE = 60  # when grill is off
SCAN_INTERVAL_BURST = 1  # after a command is sent
SCAN_BURST_DURATION = 30  # how long burst mode lasts (seconds)

# Config keys
CONF_EMAIL = "email"
CONF_PASSWORD = "password"

# Grill modes
GRILL_MODE_OFF = "off"
GRILL_MODE_GRILL = "grill"
GRILL_MODE_SMOKE = "smoke"
GRILL_MODE_PIZZA = "pizza"

# Temperature limits (Fahrenheit)
MIN_TEMP_F = 150
MAX_TEMP_F = 500
MIN_TEMP_C = 65
MAX_TEMP_C = 260
