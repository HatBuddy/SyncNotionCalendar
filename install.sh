#!/bin/bash

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Function to print status messages
status() {
    echo -e "${GREEN}[*]${NC} $1"
}

# Function to print warnings
warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Function to print errors and exit
error() {
    echo -e "${RED}[ERROR]${NC} $1"
    exit 1
}

# Check if Python 3 is installed
PYTHON_PATH=$(which python3 2>/dev/null || which python 2>/dev/null || echo "python3 not found")
if [ "$PYTHON_PATH" == "python3 not found" ]; then
    error "Python 3 not found. Please install Python 3 and try again."
fi

# Verify Python version
PYTHON_VERSION=$($PYTHON_PATH -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
if [ "$(echo "$PYTHON_VERSION < 3.7" | bc -l)" -eq 1 ]; then
    error "Python 3.7 or higher is required. Found Python $PYTHON_VERSION"
fi

# Install required packages
status "Installing required Python packages..."
$PYTHON_PATH -m pip install -q --upgrade pip
$PYTHON_PATH -m pip install -q -r requirements.txt

# Create main script
status "Creating sync script..."
MAIN_SCRIPT="$(pwd)/main.py"
cat > syncNotionCalendar.zsh << EOF
#!/bin/zsh
# Sync Notion databases with Apple Calendar
cd "$(pwd)" && \
$PYTHON_PATH "$MAIN_SCRIPT"
EOF
chmod +x syncNotionCalendar.zsh

# Check for config.ini
if [ ! -f "config.ini" ]; then
    warning "No config.ini found. Creating a default configuration..."
    cat > config.ini << 'EOL'
[GLOBAL]
# Notion API Token (starts with 'ntn_' for public integration)
NOTION_TOKEN = your_notion_token_here

# Name of your Apple Calendar (case-sensitive)
APPLE_CALENDAR = your_calendar_name_here

[DATABASES]
# Add your database IDs below (one per line)
# Format: db_1 = your_database_id_here
db_1 = your_database_id_here
EOL
    
    echo -e "\n${YELLOW}Please edit config.ini with your Notion token, calendar name, and database IDs.${NC}"
    echo -e "Then run this script again to complete the setup.\n"
    
    # Open the config file in the default editor if possible
    if [ -n "$EDITOR" ]; then
        $EDITOR config.ini
    elif command -v nano &> /dev/null; then
        nano config.ini
    elif command -v vim &> /dev/null; then
        vim config.ini
    fi
    
    echo -e "\n${GREEN}Configuration saved to config.ini${NC}"
    echo -e "Run './syncNotionCalendar.zsh' to perform the initial sync.\n"
    exit 0
fi

# Validate config.ini
status "Validating configuration..."
if ! $PYTHON_PATH -c "
import configparser
import sys

try:
    config = configparser.ConfigParser()
    if not config.read('config.ini'):
        print('Error: Could not read config.ini')
        sys.exit(1)
        
    if not config.has_section('GLOBAL') or not config.has_section('DATABASES'):
        print('Error: Missing required sections in config.ini')
        sys.exit(1)
        
    if not config.get('GLOBAL', 'NOTION_TOKEN', fallback='').strip() or \
       not config.get('GLOBAL', 'APPLE_CALENDAR', fallback='').strip():
        print('Error: Missing required values in [GLOBAL] section')
        sys.exit(1)
        
    # Check if any database IDs are configured
    has_dbs = any(v.strip() for k, v in config.items('DATABASES') 
                 if not k.startswith('#') and v.strip() and not v.strip().startswith('your_'))
    if not has_dbs:
        print('Error: No valid database IDs found in [DATABASES] section')
        sys.exit(1)
        
except Exception as e:
    print(f'Error validating config.ini: {str(e)}')
    sys.exit(1)"; then
    error "Invalid configuration in config.ini. Please check the file and try again."
fi

# Initialize configuration
status "Loading configuration..."
if ! $PYTHON_PATH src/init_conf.py config.ini; then
    error "Failed to load configuration. Please check the error messages above."
fi

# Initialize cron job
status "Setting up automatic synchronization..."
if [ -f "src/init_cron.py" ]; then
    if $PYTHON_PATH src/init_cron.py; then
        status "Automatic synchronization set up successfully"
    else
        warning "Failed to set up automatic synchronization. You may need to run synchronizations manually."
    fi
else
    warning "init_cron.py not found. Skipping cron job setup."
fi

# Initial sync
status "Performing initial synchronization..."
if ./syncNotionCalendar.zsh; then
    echo -e "\n${GREEN}Installation complete!${NC}"
    echo "Your Notion databases are now synced with your Apple Calendar."
    echo -e "\nTo manually sync at any time, run: ${YELLOW}./syncNotionCalendar.zsh${NC}"
else
    warning "Initial sync failed. Please check the error messages above."
    echo -e "\nYou can try running the sync manually with: ${YELLOW}./syncNotionCalendar.zsh${NC}"
    exit 1
fi
