#!/bin/bash
# VM Setup Script for Badge GIF Generator
# This script is run by the Custom Script Extension during VM deployment
# It pulls the application code from GitHub instead of embedding it inline
#
# Environment variables set by Bicep deployment:
#   CERT_EMAIL - Email for Let's Encrypt certificate
#   CERT_DOMAIN - DNS domain name for the VM
#   STORAGE_ACCOUNT_NAME - Azure Storage account name
#   GITHUB_REPO - GitHub repository URL (default: https://github.com/YOUR_ORG/badge-gif-generator)
#   GITHUB_BRANCH - Git branch to use (default: main)

set -e

# Log file
LOG_FILE="/var/log/badge-gif-setup.log"
exec > >(tee -a $LOG_FILE) 2>&1

echo "=========================================="
echo "Badge GIF Generator VM Setup"
echo "Started: $(date)"
echo "CERT_DOMAIN: ${CERT_DOMAIN:-not set}"
echo "CERT_EMAIL: ${CERT_EMAIL:-not set}"
echo "STORAGE_ACCOUNT_NAME: ${STORAGE_ACCOUNT_NAME:-not set}"
echo "GITHUB_REPO: ${GITHUB_REPO:-not set}"
echo "GITHUB_BRANCH: ${GITHUB_BRANCH:-main}"
echo "=========================================="

# Default GitHub repo if not set
GITHUB_REPO="${GITHUB_REPO:-https://github.com/MicrosoftAzureAaron/badge-gif-generator.git}"
GITHUB_BRANCH="${GITHUB_BRANCH:-main}"

# Update system
echo "Updating system packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get upgrade -y

# Install dependencies
echo "Installing dependencies..."
DEBIAN_FRONTEND=noninteractive apt-get install -y \
    python3.11 \
    python3.11-venv \
    python3-pip \
    nginx \
    git \
    curl \
    unzip \
    certbot \
    python3-certbot-nginx

# Install Azure CLI
echo "Installing Azure CLI..."
curl -sL https://aka.ms/InstallAzureCLIDeb | bash

# Application directory
APP_DIR="/opt/badge-gif-generator"
REPO_DIR="/opt/badge-gif-repo"

# Clone or update repository
echo "Cloning repository from GitHub..."
if [ -d "$REPO_DIR" ]; then
    cd $REPO_DIR
    git fetch origin
    git checkout $GITHUB_BRANCH
    git pull origin $GITHUB_BRANCH
else
    git clone --branch $GITHUB_BRANCH $GITHUB_REPO $REPO_DIR
fi

# Create app directory structure
echo "Setting up application directory: $APP_DIR"
mkdir -p $APP_DIR/api
mkdir -p $APP_DIR/frontend
mkdir -p $APP_DIR/shared

# Copy application files from repo
echo "Copying application files..."
cp -r $REPO_DIR/azure-vm/api/* $APP_DIR/api/
cp -r $REPO_DIR/shared/frontend/* $APP_DIR/frontend/
cp -r $REPO_DIR/shared/*.py $APP_DIR/shared/

# Create Python virtual environment
echo "Creating Python virtual environment..."
python3.11 -m venv $APP_DIR/venv

# Install Python packages
echo "Installing Python packages..."
$APP_DIR/venv/bin/pip install --upgrade pip
$APP_DIR/venv/bin/pip install -r $APP_DIR/api/requirements.txt

# Ensure PYTHONPATH includes shared module
echo 'PYTHONPATH="/opt/badge-gif-generator"' >> /etc/environment.d/badge-gif.conf

# Set storage account name in environment
echo "Configuring environment..."
cat > /etc/environment.d/badge-gif.conf << EOF
STORAGE_ACCOUNT_NAME=${STORAGE_ACCOUNT_NAME}
EOF

# Configure systemd service
echo "Configuring systemd service..."
cat > /etc/systemd/system/badge-gif-generator.service << EOF
[Unit]
Description=Badge GIF Generator Web Server
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=$APP_DIR/api
Environment="STORAGE_ACCOUNT_NAME=${STORAGE_ACCOUNT_NAME}"
ExecStart=$APP_DIR/venv/bin/uvicorn main_vm:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# Set permissions
echo "Setting permissions..."
chown -R www-data:www-data $APP_DIR/frontend
chmod -R 755 $APP_DIR/frontend

# Configure nginx
echo "Configuring nginx..."
NGINX_DOMAIN="${CERT_DOMAIN:-_}"

cat > /etc/nginx/sites-available/badge-gif-generator << EOF
server {
    listen 80;
    server_name $NGINX_DOMAIN;

    # Frontend static files
    location / {
        root $APP_DIR/frontend;
        index index.html;
        try_files \$uri \$uri/ /index.html;
    }

    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_cache_bypass \$http_upgrade;
        proxy_read_timeout 300s;
        proxy_connect_timeout 75s;
        client_max_body_size 50M;
    }

    # Health check
    location /health {
        proxy_pass http://127.0.0.1:8000/api/health;
    }
}
EOF

# Enable nginx site
ln -sf /etc/nginx/sites-available/badge-gif-generator /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default

# Test nginx configuration
nginx -t

# Start services
echo "Starting services..."
systemctl daemon-reload
systemctl enable badge-gif-generator
systemctl start badge-gif-generator
systemctl restart nginx

# Wait for service to be ready
echo "Waiting for service to start..."
sleep 5

# Seed storage account with badges from repo if needed
echo "Checking if storage needs to be seeded..."
if [ -n "$STORAGE_ACCOUNT_NAME" ] && [ -d "$REPO_DIR/assets/badges" ]; then
    echo "Seeding storage account with badges from repository..."
    
    # Use managed identity to authenticate
    az login --identity --allow-no-subscriptions
    
    # Check if badges container exists and has content
    BADGE_COUNT=$(az storage blob list \
        --account-name "$STORAGE_ACCOUNT_NAME" \
        --container-name "ms-badges" \
        --auth-mode login \
        --query "length(@)" \
        --output tsv 2>/dev/null || echo "0")
    
    if [ "$BADGE_COUNT" = "0" ] || [ -z "$BADGE_COUNT" ]; then
        echo "Storage is empty, uploading badges from repository..."
        
        # Create containers if they don't exist
        az storage container create \
            --account-name "$STORAGE_ACCOUNT_NAME" \
            --name "ms-badges" \
            --auth-mode login 2>/dev/null || true
        
        az storage container create \
            --account-name "$STORAGE_ACCOUNT_NAME" \
            --name "ms-logos" \
            --auth-mode login 2>/dev/null || true
        
        # Upload badges
        if [ -d "$REPO_DIR/assets/badges" ] && [ "$(ls -A $REPO_DIR/assets/badges)" ]; then
            echo "Uploading badges..."
            az storage blob upload-batch \
                --account-name "$STORAGE_ACCOUNT_NAME" \
                --destination "ms-badges" \
                --source "$REPO_DIR/assets/badges" \
                --auth-mode login \
                --overwrite false 2>/dev/null || true
        fi
        
        # Upload logos
        if [ -d "$REPO_DIR/assets/logos" ] && [ "$(ls -A $REPO_DIR/assets/logos)" ]; then
            echo "Uploading logos..."
            az storage blob upload-batch \
                --account-name "$STORAGE_ACCOUNT_NAME" \
                --destination "ms-logos" \
                --source "$REPO_DIR/assets/logos" \
                --auth-mode login \
                --overwrite false 2>/dev/null || true
        fi
        
        echo "Storage seeding complete!"
    else
        echo "Storage already has $BADGE_COUNT badges, skipping seed."
    fi
fi

# Setup HTTPS with Let's Encrypt
CERT_EMAIL="${CERT_EMAIL:-}"

if [ -z "$CERT_EMAIL" ]; then
    echo "No CERT_EMAIL provided, skipping automatic HTTPS setup."
    echo "Run manually: sudo certbot --nginx -d $CERT_DOMAIN --email your-email@example.com"
else
    echo "Attempting to setup HTTPS certificate..."
    # Wait for DNS propagation
    sleep 10
    
    if certbot --nginx -d "$CERT_DOMAIN" --non-interactive --agree-tos --email "$CERT_EMAIL" --redirect 2>/dev/null; then
        echo "HTTPS certificate installed successfully!"
    else
        echo "Certbot failed (DNS may not be ready yet)."
        echo "Run manually after deployment: sudo certbot --nginx -d $CERT_DOMAIN --email $CERT_EMAIL"
    fi
fi

echo "=========================================="
echo "Setup Complete!"
echo "Finished: $(date)"
echo ""
echo "Application URL: http://$CERT_DOMAIN"
echo "After HTTPS setup: https://$CERT_DOMAIN"
echo ""
echo "To update code from GitHub:"
echo "  cd $REPO_DIR && git pull"
echo "  sudo cp -r api/* $APP_DIR/api/"
echo "  sudo cp -r frontend/* $APP_DIR/frontend/"
echo "  sudo systemctl restart badge-gif-generator"
echo ""
echo "To setup HTTPS manually:"
echo "  sudo certbot --nginx -d $CERT_DOMAIN --email your-email@example.com"
echo "=========================================="
