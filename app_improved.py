import os
import sqlite3
import json
import logging
from functools import wraps
from datetime import datetime
from flask import Flask, request, render_template_string, jsonify, redirect, url_for, abort

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False

DB_FILE = "sapakata_hub.db"
MAX_SEARCH_LENGTH = 100
MAX_SEARCH_QUERY_LENGTH = 50

class DatabaseError(Exception):
    """Custom exception for database-related errors."""
    pass

class ValidationError(Exception):
    """Custom exception for validation errors."""
    pass

def get_db_connection():
    """
    Establishes connection to the SQLite database with row factory for dictionary-like access.
    Includes error handling for connection failures.
    """
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    except sqlite3.DatabaseError as e:
        logger.error(f"Database connection error: {str(e)}")
        raise DatabaseError(f"Failed to connect to database: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error connecting to database: {str(e)}")
        raise DatabaseError(f"Unexpected database error: {str(e)}")

def safe_db_operation(func):
    """Decorator to safely handle database operations with transaction rollback."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        conn = None
        try:
            conn = get_db_connection()
            result = func(conn, *args, **kwargs)
            conn.commit()
            return result
        except sqlite3.IntegrityError as e:
            if conn:
                conn.rollback()
            logger.error(f"Database integrity error: {str(e)}")
            raise DatabaseError(f"Data integrity violation: {str(e)}")
        except sqlite3.OperationalError as e:
            if conn:
                conn.rollback()
            logger.error(f"Database operational error: {str(e)}")
            raise DatabaseError(f"Database operation failed: {str(e)}")
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Unexpected error in database operation: {str(e)}")
            raise
        finally:
            if conn:
                conn.close()
    return wrapper

def validate_string_input(value, max_length=MAX_SEARCH_QUERY_LENGTH, field_name="input"):
    """
    Sanitize and validate string inputs to prevent injection attacks.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{field_name} must be a string")
    
    value = value.strip()
    
    if len(value) > max_length:
        raise ValidationError(f"{field_name} exceeds maximum length of {max_length} characters")
    
    # Check for suspicious SQL patterns (basic check)
    suspicious_patterns = ["';", "\"", "/*", "*/", "--", "xp_", "sp_"]
    if any(pattern in value.lower() for pattern in suspicious_patterns):
        logger.warning(f"Suspicious input detected in {field_name}: {value[:50]}")
        raise ValidationError(f"Invalid characters detected in {field_name}")
    
    return value

def validate_integer_input(value, min_val=1, max_val=None, field_name="value"):
    """Validate and sanitize integer inputs."""
    try:
        int_val = int(value)
        if int_val < min_val:
            raise ValidationError(f"{field_name} must be at least {min_val}")
        if max_val is not None and int_val > max_val:
            raise ValidationError(f"{field_name} must not exceed {max_val}")
        return int_val
    except (TypeError, ValueError):
        raise ValidationError(f"{field_name} must be a valid integer")

@safe_db_operation
def init_db(conn):
    """
    Initializes the database schemas and seeds default datasets for Sapakata's Jambi hub.
    Improved with better error handling and schema validation.
    """
    try:
        cursor = conn.cursor()
        
        # 1. Create Creators/Portfolio Index
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS creators (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                category TEXT NOT NULL,
                skills TEXT NOT NULL,
                bio TEXT NOT NULL,
                location TEXT NOT NULL,
                contact TEXT NOT NULL,
                badge TEXT NOT NULL,
                badge_color TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 2. Create Kedai C.H Menu Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS menu_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                description TEXT NOT NULL,
                price INTEGER NOT NULL,
                category TEXT NOT NULL,
                icon TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # 3. Create Space Bookings Table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                space_type TEXT NOT NULL,
                duration INTEGER NOT NULL,
                pax INTEGER NOT NULL,
                catering TEXT NOT NULL,
                total_price INTEGER NOT NULL,
                booking_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Check if database is empty, seed mock data if so
        cursor.execute("SELECT COUNT(*) FROM creators")
        creator_count = cursor.fetchone()[0]
        
        if creator_count == 0:
            logger.info("Seeding initial database with mock data")
            
            # Seed creators
            creators_data = [
                ("Indra Gunawan", "UI/UX Designer", "BrandDesign", "Figma, Wireframing, Sumatra Coffee e-Commerce UI", 
                 "Modern visual layout overhaul focused on high checkout conversions and native mobile optimization.", 
                 "Jambi, Telanaipura", "Indra Gunawan", "UI/UX CASE", "neonOrange"),
                ("Sapakata Studio", "Creative Agency", "BrandDesign", "Packaging, Full Corporate Identity, Visual Standard Documents", 
                 "Full corporate visual language development, packaging designs, and menu layout standards for commercial spots.", 
                 "Hub Resident", "Sapakata Studio", "CRAFT BRANDING", "emerald-400"),
                ("Rizky Alfarizi", "Videographer & Motion Artist", "Videography", "Cinematic Reels, Premiere Pro, Color Grading, Product Shoots", 
                 "High-impact dynamic commercial video showcasing standard daily hub operations and customer lounge environment.", 
                 "Jambi, Sipin", "Rizky Alfarizi", "PROD REEL", "blue-400")
            ]
            
            cursor.executemany('''
                INSERT INTO creators (name, role, category, skills, bio, location, contact, badge, badge_color)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', creators_data)
            
            # Seed Menu Items
            menu_data = [
                ("Signature Kopi Susu Aren", "Espresso, premium palm sugar syrup, full cream milk.", 18000, "coffee", "coffee"),
                ("Manual Brew V60", "Locally-sourced single-origin Kerinci beans, hand poured.", 22000, "coffee", "filter_vintage"),
                ("Signature Matcha Latte", "Ceremonial grade green tea blend, steamed fresh milk.", 20000, "non-coffee", "bubble_chart"),
                ("Tempeh Crispy Fries", "Deep-fried crisp savory Jambi-sourced tempeh bites with home chili sauce.", 15000, "snacks", "restaurant")
            ]
            
            cursor.executemany('''
                INSERT INTO menu_items (name, description, price, category, icon)
                VALUES (?, ?, ?, ?, ?)
            ''', menu_data)
            
            logger.info("Database seeding completed successfully")
    
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise DatabaseError(f"Failed to initialize database: {str(e)}")

# Initialize the database immediately on launch
try:
    init_db()
    logger.info("Database initialized successfully")
except DatabaseError as e:
    logger.error(f"Failed to initialize database on startup: {str(e)}")
    # Continue anyway - database might already exist

@app.context_processor
def utility_processor():
    """Injects helpful formatting utilities directly into Jinja templates."""
    def format_idr(value):
        try:
            return f"IDR {int(value):,.0f}".replace(",", ".")
        except (ValueError, TypeError):
            logger.warning(f"Invalid value for IDR formatting: {value}")
            return "IDR 0"
    
    def escape_html(text):
        """Basic HTML escaping for template safety."""
        if not isinstance(text, str):
            return str(text)
        return (text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                    .replace('"', "&quot;")
                    .replace("'", "&#x27;"))
    
    return dict(format_idr=format_idr, escape_html=escape_html)

@app.errorhandler(DatabaseError)
def handle_database_error(error):
    """Handle database-related errors."""
    logger.error(f"Database error: {str(error)}")
    return jsonify({"error": "Database operation failed. Please try again later."}), 500

@app.errorhandler(ValidationError)
def handle_validation_error(error):
    """Handle validation errors."""
    logger.warning(f"Validation error: {str(error)}")
    return jsonify({"error": str(error)}), 400

@app.errorhandler(404)
def handle_not_found(error):
    """Handle 404 errors."""
    return jsonify({"error": "Resource not found"}), 404

@app.errorhandler(500)
def handle_server_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {str(error)}")
    return jsonify({"error": "Internal server error. Please try again later."}), 500

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="X-UA-Compatible" content="ie=edge">
    <title>Sapakata Creative Hub - Python Engine</title>
    
    <!-- Tailwind CSS -->
    <script src="https://cdn.tailwindcss.com"></script>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        charcoal: '#121212',
                        zincDark: '#0D0D0D',
                        neonOrange: '#FF5A1F',
                        neonMint: '#10B981',
                        accentGray: '#1F1F1F',
                        mutedText: '#A1A1AA'
                    },
                    fontFamily: {
                        sans: ['Google Sans', 'Roboto', 'sans-serif'],
                        mono: ['Google Sans Code', 'monospace']
                    }
                }
            }
        }
    </script>
    
    <!-- HTMX for AJAX interactions -->
    <script src="https://unpkg.com/htmx.org@1.9.10"></script>
    
    <!-- Material Icons & Google Sans Font -->
    <link href="https://fonts.googleapis.com/css2?family=Material+Icons" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Google+Sans:wght@300;400;500;700;900&display=swap" rel="stylesheet">
    
    <style>
        body {
            font-family: 'Google Sans', 'Roboto', sans-serif;
            background-color: #0d0d0d;
            color: #ffffff;
            overflow-x: hidden;
        }
        .text-glow-orange {
            text-shadow: 0 0 10px rgba(255, 90, 31, 0.5), 0 0 20px rgba(255, 90, 31, 0.2);
        }
        .text-stroke-focus {
            -webkit-text-stroke: 1.5px #FF5A1F;
            color: transparent;
        }
        .no-scrollbar::-webkit-scrollbar {
            display: none;
        }
    </style>
</head>
<body class="h-screen w-screen flex flex-col overflow-hidden bg-zincDark text-white">

    <!-- Top Status Bar -->
    <header class="h-14 bg-black border-b border-zinc-800 px-4 flex items-center justify-between z-50 shrink-0">
        <div class="flex items-center gap-3">
            <span class="material-icons text-neonOrange">architecture</span>
            <div>
                <span class="font-bold text-sm tracking-wide">SAPAKATA PYTHON ENGINE</span>
                <span class="text-xs text-zinc-500 ml-2 font-mono">v2.1 (Flask & SQLite3 Active)</span>
            </div>
        </div>
        
        <div class="flex items-center bg-zinc-900 rounded-full p-1 border border-zinc-800">
            <button class="px-4 py-1.5 rounded-full text-xs font-semibold flex items-center gap-2 bg-neonOrange text-white">
                <span class="material-icons text-xs">dns</span> Jambi Main Node
            </button>
        </div>

        <div class="flex items-center gap-4">
            <div class="hidden md:flex items-center gap-2 text-xs text-zinc-400 font-mono">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Online (Telanaipura)
            </div>
            <a href="https://wa.me/6282321963638" target="_blank" rel="noopener noreferrer" class="bg-zinc-800 hover:bg-zinc-700 text-xs py-1.5 px-3 rounded-md transition-colors flex items-center gap-1">
                <span class="material-icons text-xs text-emerald-500">phone</span> Contact Admin
            </a>
        </div>
    </header>

    <!-- App Main Body with left sidebar navigation -->
    <div class="flex-grow flex min-h-0 overflow-hidden">
        
        <!-- Sidebar Navigation Left -->
        <aside class="w-64 bg-black border-r border-zinc-900 flex flex-col p-4 shrink-0 hidden lg:flex">
            <div class="mb-6">
                <h3 class="text-xs font-bold text-zinc-500 uppercase tracking-widest mb-3">Sections</h3>
                <nav class="space-y-1">
                    <button onclick="switchSection('home')" id="nav-home" class="w-full flex items-center justify-between p-2.5 rounded-lg bg-accentGray text-neonOrange text-sm font-medium transition-all">
                        <span class="flex items-center gap-2">
                            <span class="material-icons text-sm">home</span> 1. Home / Portal
                        </span>
                    </button>
                    <button onclick="switchSection('directory')" id="nav-directory" class="w-full flex items-center justify-between p-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 text-sm font-medium transition-all">
                        <span class="flex items-center gap-2">
                            <span class="material-icons text-sm">people</span> 2. Creator Directory
                        </span>
                    </button>
                    <button onclick="switchSection('menu')" id="nav-menu" class="w-full flex items-center justify-between p-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 text-sm font-medium transition-all">
                        <span class="flex items-center gap-2">
                            <span class="material-icons text-sm">local_cafe</span> 3. Cafe Menu
                        </span>
                        <span class="text-[10px] bg-emerald-950 text-emerald-400 px-1.5 py-0.5 rounded font-mono">Kedai</span>
                    </button>
                    <button onclick="switchSection('booking')" id="nav-booking" class="w-full flex items-center justify-between p-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 text-sm font-medium transition-all">
                        <span class="flex items-center gap-2">
                            <span class="material-icons text-sm">event_seat</span> 4. Space Booking
                        </span>
                        <span class="text-[10px] bg-orange-950 text-neonOrange px-1.5 py-0.5 rounded font-mono">Book</span>
                    </button>
                </nav>
            </div>

            <!-- Jambi Coordinates Context -->
            <div class="mt-auto border-t border-zinc-800 pt-4">
                <div class="p-3 bg-zinc-950 rounded-lg border border-zinc-800">
                    <span class="text-[10px] uppercase font-bold text-neonOrange tracking-widest">Hub Location</span>
                    <p class="text-xs font-semibold mt-1">Sapakata Creative Hub</p>
                    <p class="text-[11px] text-zinc-500 mt-1">Pematang Sulur, Kec. Telanaipura, Kota Jambi, Indonesia 36129</p>
                    <p class="text-[11px] text-zinc-400 font-mono mt-2">⏱ 09:00 - 23:00 Daily</p>
                </div>
            </div>
        </aside>

        <!-- Dynamic Simulated Canvas (Center) -->
        <main class="flex-grow bg-zinc-950 flex flex-col items-center justify-start overflow-y-auto p-4 md:p-8">
            
            <!-- Mobile Responsive Top Menu -->
            <div class="lg:hidden w-full max-w-4xl flex gap-1 bg-zinc-900 p-1 rounded-lg mb-4 border border-zinc-800 overflow-x-auto no-scrollbar">
                <button onclick="switchSection('home')" id="m-nav-home" class="flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap bg-accentGray text-neonOrange">Home</button>
                <button onclick="switchSection('directory')" id="m-nav-directory" class="flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap text-zinc-400">Directory</button>
                <button onclick="switchSection('menu')" id="m-nav-menu" class="flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap text-zinc-400">Cafe Menu</button>
                <button onclick="switchSection('booking')" id="m-nav-booking" class="flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap text-zinc-400">Book Space</button>
            </div>

            <div class="w-full max-w-5xl bg-charcoal border border-zinc-800 rounded-2xl shadow-2xl flex flex-col overflow-hidden min-h-[600px] relative">
                
                <!-- Inner Simulated Navigation Header -->
                <nav class="sticky top-0 bg-charcoal/95 backdrop-blur-md border-b border-zinc-900 px-6 py-4 flex items-center justify-between z-40">
                    <div class="flex items-center gap-3">
                        <div class="w-9 h-9 rounded-lg bg-zinc-900 border border-zinc-800 flex items-center justify-center font-bold tracking-widest text-neonOrange text-sm">
                            CH
                        </div>
                        <div class="flex flex-col">
                            <span class="font-black text-sm tracking-widest uppercase">SAPAKATA</span>
                            <span class="text-[10px] text-zinc-400 uppercase tracking-widest -mt-1 font-medium">Creative Hub</span>
                        </div>
                    </div>

                    <div class="hidden md:flex items-center gap-6">
                        <button onclick="switchSection('home')" class="text-xs font-bold tracking-widest uppercase hover:text-neonOrange transition-colors">Home</button>
                        <button onclick="switchSection('directory')" class="text-xs font-bold tracking-widest uppercase hover:text-neonOrange transition-colors">Directory</button>
                        <button onclick="switchSection('menu')" class="text-xs font-bold tracking-widest uppercase hover:text-neonOrange transition-colors">Kedai C.H</button>
                        <button onclick="switchSection('booking')" class="text-xs font-bold tracking-widest uppercase hover:text-neonOrange transition-colors">Book Space</button>
                    </div>

                    <div>
                        <button onclick="switchSection('booking')" class="bg-neonOrange hover:bg-orange-600 text-white font-bold tracking-wider text-[11px] uppercase py-2 px-4 rounded transition-all duration-200">
                            Book Table
                        </button>
                    </div>
                </nav>

                <!-- SECTION 1: HOME/PORTAL PAGE -->
                <div id="section-home" class="section-panel block">
                    <div class="relative py-16 md:py-24 px-6 md:px-12 border-b border-zinc-900 overflow-hidden flex flex-col items-center text-center bg-gradient-to-b from-zincDark via-charcoal to-charcoal">
                        <div class="absolute inset-0 opacity-5 pointer-events-none bg-[radial-gradient(#fff_1px,transparent_1px)] [background-size:16px_16px]"></div>
                        
                        <span class="text-[11px] font-mono tracking-widest uppercase text-neonOrange px-3 py-1 bg-neonOrange/10 border border-neonOrange/20 rounded-full mb-6">
                            📍 Telanaipura, Jambi Hub Operations
                        </span>
                        
                        <h1 class="text-4xl md:text-6xl font-black tracking-tighter uppercase mb-6 leading-none max-w-4xl">
                            YOUR DAILY BREW & <br>
                            <span class="text-stroke-focus text-glow-orange">CREATIVE SPACE</span> <br>
                            IN JAMBI
                        </h1>
                        
                        <p class="text-sm md:text-base text-mutedText max-w-2xl mb-8 leading-relaxed">
                            Sapakata Creative Hub integrates Jambi's top professional freelance talent with a custom culinary coffee shop. Work, play, connect, and thrive under one roof.
                        </p>

                        <div class="flex flex-col sm:flex-row gap-4 justify-center">
                            <button onclick="switchSection('booking')" class="bg-neonOrange hover:bg-orange-600 text-white font-bold tracking-widest text-xs uppercase py-3.5 px-8 rounded-lg shadow-lg shadow-neonOrange/20 transition-all duration-200">
                                Reserve Space Packages
                            </button>
                            <button onclick="switchSection('menu')" class="bg-zinc-900 hover:bg-zinc-800 text-white border border-zinc-800 font-bold tracking-widest text-xs uppercase py-3.5 px-8 rounded-lg transition-all duration-200">
                                Explore Kedai Menu
                            </button>
                        </div>
                    </div>

                    <!-- Highlighted Info Cards -->
                    <div class="py-12 px-6 md:px-12 max-w-6xl mx-auto">
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
                            <div class="bg-zinc-900/50 p-6 rounded-xl border border-zinc-800 flex flex-col gap-4">
                                <span class="material-icons text-3xl text-neonOrange">co_present</span>
                                <h3 class="text-lg font-bold tracking-tight">Active Creative Hub</h3>
                                <p class="text-xs text-mutedText leading-relaxed">High-speed workspaces, robust power grids, and discussion spaces optimized for students, agencies, and professionals.</p>
                            </div>
                            <div class="bg-zinc-900/50 p-6 rounded-xl border border-zinc-800 flex flex-col gap-4">
                                <span class="material-icons text-3xl text-neonOrange">local_pizza</span>
                                <h3 class="text-lg font-bold tracking-tight">Kedai CH Dining</h3>
                                <p class="text-xs text-mutedText leading-relaxed">Hand-crafted local coffees, signature matcha lattes, and savory snacks prepared fresh in Telanaipura.</p>
                            </div>
                            <div class="bg-zinc-900/50 p-6 rounded-xl border border-zinc-800 flex flex-col gap-4">
                                <span class="material-icons text-3xl text-neonOrange">emoji_people</span>
                                <h3 class="text-lg font-bold tracking-tight">Industry Directory</h3>
                                <p class="text-xs text-mutedText leading-relaxed">A public portfolio ecosystem highlighting local Jambi creators, designers, and multimedia specialists.</p>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- SECTION 2: CREATOR DIRECTORY -->
                <div id="section-directory" class="section-panel hidden">
                    <div class="py-12 px-6 md:px-12 max-w-5xl mx-auto">
                        <div class="mb-8">
                            <span class="text-[10px] uppercase font-bold tracking-widest text-neonOrange">Jambi's Local Talents</span>
                            <h1 class="text-3xl font-black tracking-tight mt-1 uppercase">Sapakata Creative Portfolio Index</h1>
                            <p class="text-xs text-mutedText mt-1">Search or filter through local agency teams, freelance designers, and active videographers operating inside Sapakata.</p>
                        </div>

                        <!-- HTMX Enabled Search & Filter Bar -->
                        <div class="flex flex-col md:flex-row gap-4 items-start md:items-center justify-between mb-8 pb-6 border-b border-zinc-900">
                            <div class="relative w-full md:w-80">
                                <span class="material-icons absolute left-3 top-2.5 text-zinc-500 text-sm">search</span>
                                <input type="text" name="search" placeholder="Type name or skill..." 
                                       maxlength="50"
                                       class="w-full bg-zinc-900 border border-zinc-800 text-xs rounded-lg py-2.5 pl-9 pr-4 focus:outline-none focus:border-neonOrange text-white"
                                       hx-get="/api/creators" 
                                       hx-trigger="keyup changed delay:300ms" 
                                       hx-target="#creators-grid"
                                       hx-include="[name='category']"
                                       hx-on="htmx:responseError: handleError('Failed to load creators')">
                            </div>
                            
                            <!-- Hidden category input for HTMX indexing inclusion -->
                            <input type="hidden" name="category" id="active-category" value="All">
                            
                            <div class="flex flex-wrap gap-2 no-scrollbar" id="directory-filter-container">
                                <button onclick="selectCategory('All')" id="cat-All" class="filter-chip bg-neonOrange text-white text-xs px-3.5 py-2 rounded-lg font-bold">All Fields</button>
                                <button onclick="selectCategory('BrandDesign')" id="cat-BrandDesign" class="filter-chip bg-zinc-900 hover:bg-zinc-800 text-zinc-400 text-xs px-3.5 py-2 rounded-lg font-bold">#BrandDesign</button>
                                <button onclick="selectCategory('Videography')" id="cat-Videography" class="filter-chip bg-zinc-900 hover:bg-zinc-800 text-zinc-400 text-xs px-3.5 py-2 rounded-lg font-bold">#Videography</button>
                            </div>
                        </div>

                        <!-- Render Grid Container -->
                        <div class="grid grid-cols-1 md:grid-cols-3 gap-6" id="creators-grid" hx-get="/api/creators" hx-trigger="load" hx-include="[name='category']">
                            <!-- Populated Dynamically by Python HTMX API -->
                            <div class="col-span-full text-center text-xs text-zinc-500 py-12">Loading Sapakata Creators Database...</div>
                        </div>
                    </div>
                </div>

                <!-- SECTION 3: KEDAI C.H DIGITAL MENU -->
                <div id="section-menu" class="section-panel hidden">
                    <div class="py-12 px-6 md:px-12 max-w-4xl mx-auto">
                        <div class="text-center mb-8 bg-zinc-900/30 p-6 rounded-2xl border border-zinc-800">
                            <span class="text-xs font-mono text-neonOrange uppercase tracking-widest font-semibold">Table ordering system</span>
                            <h1 class="text-2xl font-black mt-1 uppercase tracking-tight">KEDAI C.H DIGITAL MENU</h1>
                            <p class="text-xs text-zinc-400 mt-2">Pick your table, adjust your favorite items, and the engine will prepare your WhatsApp checkout order.</p>
                            
                            <div class="mt-4 flex flex-col sm:flex-row items-center justify-center gap-2 bg-charcoal p-3 rounded-lg border border-zinc-800 max-w-sm mx-auto">
                                <span class="text-xs font-bold tracking-wider uppercase text-zinc-400 shrink-0">Your Table:</span>
                                <select id="menu-table-select" onchange="recalculateCart()" class="bg-zinc-900 border border-zinc-700 text-xs px-3 py-1.5 rounded text-white focus:outline-none focus:border-neonOrange">
                                    <option value="Table 01 (Indoor Lounge)">Table 01 (Indoor Lounge)</option>
                                    <option value="Table 02 (Indoor Window)">Table 02 (Indoor Window)</option>
                                    <option value="Table 03 (Co-working Bench)">Table 03 (Co-working Bench)</option>
                                    <option value="Table 04 (Outdoor Garden)">Table 04 (Outdoor Garden)</option>
                                </select>
                            </div>
                        </div>

                        <!-- Category Filters for Menu -->
                        <div class="flex gap-1 bg-zinc-900 p-1 rounded-lg border border-zinc-800 mb-6 overflow-x-auto no-scrollbar">
                            <button onclick="filterMenuCategory('all')" id="menu-cat-all" class="menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold bg-accentGray text-neonOrange">All Items</button>
                            <button onclick="filterMenuCategory('coffee')" id="menu-cat-coffee" class="menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold text-zinc-400">Coffee Signature</button>
                            <button onclick="filterMenuCategory('non-coffee')" id="menu-cat-non-coffee" class="menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold text-zinc-400">Non-Coffee</button>
                            <button onclick="filterMenuCategory('snacks')" id="menu-cat-snacks" class="menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold text-zinc-400">Snacks</button>
                        </div>

                        <!-- Food & Beverage items fetched from SQLite database dynamically -->
                        <div class="space-y-4" id="menu-list-container">
                            {% for item in menu_items %}
                            <div class="menu-card flex justify-between items-center bg-zinc-900/50 p-4 rounded-xl border border-zinc-800 hover:border-zinc-700 transition-all" data-category="{{ item.category }}">
                                <div class="flex gap-4 items-center">
                                    <div class="w-12 h-12 rounded-lg bg-zinc-800 border border-zinc-700 flex items-center justify-center text-neonOrange">
                                        <span class="material-icons text-xl">{{ item.icon }}</span>
                                    </div>
                                    <div>
                                        <h3 class="font-bold text-sm text-white">{{ item.name }}</h3>
                                        <p class="text-[11px] text-zinc-400 mt-0.5">{{ item.description }}</p>
                                        <span class="text-xs text-neonOrange font-mono font-bold block mt-1" data-price="{{ item.price }}">{{ format_idr(item.price) }}</span>
                                    </div>
                                </div>
                                <div class="flex items-center gap-3">
                                    <button onclick="updateCart('{{ item.id }}', '{{ escape_html(item.name) }}', {{ item.price }}, -1)" class="w-8 h-8 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-sm font-black transition-colors">-</button>
                                    <span id="qty-{{ item.id }}" class="w-4 text-center font-mono font-bold text-sm">0</span>
                                    <button onclick="updateCart('{{ item.id }}', '{{ escape_html(item.name) }}', {{ item.price }}, 1)" class="w-8 h-8 rounded-full bg-zinc-800 hover:bg-zinc-700 flex items-center justify-center text-sm font-black transition-colors">+</button>
                                </div>
                            </div>
                            {% endfor %}
                        </div>

                        <!-- Real-time Cart and WhatsApp Engine powered by backend calc -->
                        <div class="mt-8 bg-zinc-900 p-6 rounded-2xl border border-zinc-800 flex flex-col md:flex-row justify-between items-center gap-6"
                             id="cart-calculations">
                            <div class="w-full md:w-auto">
                                <span class="text-[10px] text-zinc-500 uppercase font-mono tracking-widest block">Cart Total</span>
                                <span class="text-2xl font-black text-neonOrange font-mono" id="display-cart-total">IDR 0</span>
                                <p class="text-[10px] text-zinc-500 mt-1">Select table and items to construct WhatsApp dispatch order payload.</p>
                            </div>
                            <div class="w-full md:w-auto">
                                <a id="whatsapp-order-btn" href="#" target="_blank" rel="noopener noreferrer" class="opacity-50 pointer-events-none w-full md:w-auto bg-emerald-600 hover:bg-emerald-700 text-white font-bold tracking-wider text-xs uppercase py-3.5 px-6 rounded-lg flex items-center justify-center gap-2 transition-all">
                                    <span class="material-icons text-sm">send</span> Order via WhatsApp
                                </a>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- SECTION 4: SPACE BOOKING -->
                <div id="section-booking" class="section-panel hidden">
                    <div class="py-12 px-6 md:px-12 max-w-4xl mx-auto">
                        <div class="mb-8">
                            <span class="text-[10px] uppercase font-bold tracking-widest text-neonOrange">Workspace Booking Simulator</span>
                            <h1 class="text-3xl font-black tracking-tight mt-1 uppercase">Sapakata Space Package Estimator</h1>
                            <p class="text-xs text-mutedText mt-1">Plan your workspace reservations and select catering bundles below. Calculations are processed directly by the Python database engine.</p>
                        </div>

                        <!-- Dynamic HTMX driven booking parameters form -->
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
                            
                            <!-- Control Panel Form -->
                            <form hx-post="/api/booking/calculate" hx-trigger="change, load" hx-target="#booking-invoice" hx-on="htmx:responseError: handleError('Failed to calculate booking')" class="space-y-6 bg-zinc-900/50 p-6 rounded-2xl border border-zinc-800">
                                
                                <div class="flex flex-col gap-2">
                                    <label class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Select Hub Zone</label>
                                    <select name="space" class="bg-charcoal border border-zinc-700 text-xs rounded-lg p-3 text-white focus:outline-none focus:border-neonOrange">
                                        <option value="discussion">Group Discussion Zone (IDR 50.000/hr)</option>
                                        <option value="communal">Communal Table (Min Food/Drink Order)</option>
                                        <option value="private">Private Studio Lounge (IDR 100.000/hr)</option>
                                    </select>
                                </div>

                                <div class="flex flex-col gap-2">
                                    <div class="flex justify-between items-center">
                                        <label class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Rental Duration</label>
                                        <span id="duration-label" class="text-xs font-mono text-neonOrange font-bold">2 Hours</span>
                                    </div>
                                    <input type="range" name="duration" min="1" max="8" value="2" 
                                           oninput="document.getElementById('duration-label').innerText = this.value + ' Hours'" 
                                           class="w-full accent-neonOrange bg-charcoal h-1 rounded-lg">
                                </div>

                                <div class="flex flex-col gap-2">
                                    <div class="flex justify-between items-center">
                                        <label class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Estimated Attendees</label>
                                        <span id="pax-label" class="text-xs font-mono text-neonOrange font-bold">5 People</span>
                                    </div>
                                    <input type="range" name="pax" min="1" max="25" value="5" 
                                           oninput="document.getElementById('pax-label').innerText = this.value + ' People'" 
                                           class="w-full accent-neonOrange bg-charcoal h-1 rounded-lg">
                                </div>

                                <div class="flex flex-col gap-2">
                                    <label class="text-xs font-bold text-zinc-400 uppercase tracking-wider">Catering Bundle Add-on (per person)</label>
                                    <select name="catering" class="bg-charcoal border border-zinc-700 text-xs rounded-lg p-3 text-white focus:outline-none focus:border-neonOrange">
                                        <option value="none">No Catering Bundling</option>
                                        <option value="coffee">Coffee + Local Snack Pack (IDR 25.000/pax)</option>
                                        <option value="meal">Heavy Meal + Iced Tea Pack (IDR 45.000/pax)</option>
                                    </select>
                                </div>
                            </form>

                            <!-- Live Python-Generated Invoice Breakdown View -->
                            <div id="booking-invoice" class="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 flex flex-col justify-between">
                                <div class="text-center text-zinc-500 py-16">
                                    Awaiting parameters inputs...
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Footer Section -->
                <footer class="bg-zincDark border-t border-zinc-900 px-6 py-8 mt-auto">
                    <div class="max-w-6xl mx-auto flex flex-col md:flex-row justify-between gap-6">
                        <div class="max-w-xs">
                            <div class="flex items-center gap-2 mb-3">
                                <div class="w-6 h-6 rounded bg-neonOrange text-[10px] font-bold text-black flex items-center justify-center tracking-widest font-mono">CH</div>
                                <span class="font-black text-xs tracking-wider uppercase">Sapakata Creative Hub</span>
                            </div>
                            <p class="text-[11px] text-zinc-400 leading-relaxed">
                                Empowering local creators and developers. Serving premium brews daily in Pematang Sulur, Telanaipura, Jambi.
                            </p>
                        </div>
                        <div class="text-xs space-y-1">
                            <h4 class="font-bold tracking-wider text-neonOrange uppercase text-[10px]">Contact & Delivery</h4>
                            <p class="text-zinc-500">⏱ Daily 09:00 - 23:00 WIB</p>
                            <p class="text-zinc-500">📞 +62 823-2196-3638</p>
                            <p class="text-zinc-500">📸 @sapakata.creativehub</p>
                        </div>
                    </div>
                </footer>
            </div>
        </main>
    </div>

    <!-- Interactive System Script with Enhanced Error Handling -->
    <script>
        // Track the virtual shopping cart inside client memory
        let cart = {};

        function handleError(message) {
            console.error(message);
            alert(message || 'An error occurred. Please try again.');
        }

        function switchSection(sectionId) {
            try {
                // Hide all views
                document.querySelectorAll('.section-panel').forEach(panel => {
                    panel.classList.add('hidden');
                    panel.classList.remove('block');
                });
                // Show active
                const activeSection = document.getElementById(`section-${sectionId}`);
                if (activeSection) {
                    activeSection.classList.remove('hidden');
                    activeSection.classList.add('block');
                }

                // Set active classes for left navigation sidebar
                document.querySelectorAll('aside nav button').forEach(btn => {
                    btn.className = "w-full flex items-center justify-between p-2.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 text-sm font-medium transition-all";
                });
                const activeSidebarBtn = document.getElementById(`nav-${sectionId}`);
                if (activeSidebarBtn) {
                    activeSidebarBtn.className = "w-full flex items-center justify-between p-2.5 rounded-lg bg-accentGray text-neonOrange text-sm font-medium transition-all";
                }

                // Set active classes for mobile responsive top banner
                document.querySelectorAll('.lg\\:hidden button').forEach(btn => {
                    btn.className = "flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap text-zinc-400";
                });
                const activeMobileBtn = document.getElementById(`m-nav-${sectionId}`);
                if (activeMobileBtn) {
                    activeMobileBtn.className = "flex-1 py-2 px-3 rounded-md text-xs font-semibold whitespace-nowrap bg-accentGray text-neonOrange";
                }
            } catch (error) {
                handleError('Failed to switch section: ' + error.message);
            }
        }

        // Handle dynamically updated search filters inside creator directory
        function selectCategory(categoryName) {
            try {
                document.getElementById('active-category').value = categoryName;
                
                // Re-style chips
                document.querySelectorAll('.filter-chip').forEach(chip => {
                    chip.className = "filter-chip bg-zinc-900 hover:bg-zinc-800 text-zinc-400 text-xs px-3.5 py-2 rounded-lg font-bold";
                });
                const activeChip = document.getElementById(`cat-${categoryName}`);
                if (activeChip) {
                    activeChip.className = "filter-chip bg-neonOrange text-white text-xs px-3.5 py-2 rounded-lg font-bold";
                }
                
                // Programmatically dispatch HTMX search input keyup event to trigger API refresh
                const searchInput = document.querySelector('[name="search"]');
                if (searchInput) {
                    searchInput.dispatchEvent(new Event('changed'));
                }
            } catch (error) {
                handleError('Failed to select category: ' + error.message);
            }
        }

        // Kedai C.H Category Filter Logic
        function filterMenuCategory(category) {
            try {
                // Re-style selection buttons
                document.querySelectorAll('.menu-filter-btn').forEach(btn => {
                    btn.className = "menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold text-zinc-400";
                });
                const activeBtn = document.getElementById(`menu-cat-${category}`);
                if (activeBtn) {
                    activeBtn.className = "menu-filter-btn flex-1 py-2 px-3 rounded-md text-xs font-bold bg-accentGray text-neonOrange";
                }

                // Filter item cards visually
                document.querySelectorAll('.menu-card').forEach(card => {
                    if (category === 'all' || card.getAttribute('data-category') === category) {
                        card.classList.remove('hidden');
                        card.classList.add('flex');
                    } else {
                        card.classList.add('hidden');
                        card.classList.remove('flex');
                    }
                });
            } catch (error) {
                handleError('Failed to filter menu: ' + error.message);
            }
        }

        // Simple Shopping Cart Logic integrating directly into dynamic layout
        function updateCart(itemId, name, price, qtyChange) {
            try {
                // Validate inputs
                if (!Number.isInteger(parseInt(itemId)) || price < 0 || !Number.isInteger(qtyChange)) {
                    throw new Error('Invalid cart parameters');
                }

                if (!cart[itemId]) {
                    cart[itemId] = { name: name, price: price, qty: 0 };
                }
                cart[itemId].qty = Math.max(0, cart[itemId].qty + qtyChange);
                const qtyDisplay = document.getElementById(`qty-${itemId}`);
                if (qtyDisplay) {
                    qtyDisplay.innerText = cart[itemId].qty;
                }
                
                recalculateCart();
            } catch (error) {
                handleError('Failed to update cart: ' + error.message);
            }
        }

        function recalculateCart() {
            try {
                let total = 0;
                let listString = [];
                
                for (let key in cart) {
                    if (cart[key].qty > 0) {
                        let sub = cart[key].qty * cart[key].price;
                        total += sub;
                        listString.push(`${cart[key].qty}x ${cart[key].name}`);
                    }
                }

                const totalDisplay = document.getElementById('display-cart-total');
                if (totalDisplay) {
                    totalDisplay.innerText = 'IDR ' + total.toLocaleString('id-ID');
                }

                const waBtn = document.getElementById('whatsapp-order-btn');
                if (!waBtn) return;
                
                if (total > 0) {
                    waBtn.classList.remove('opacity-50', 'pointer-events-none');
                    const tableSelect = document.getElementById('menu-table-select');
                    const tableNum = tableSelect ? tableSelect.value : 'Unknown Table';
                    const message = `Halo Sapakata Kedai! Saya berada di ${tableNum}. Berikut rincian pesanan saya:\n\n${listString.join('\n')}\n\n*Total Estimasi:* IDR ${total.toLocaleString('id-ID')}\n\nMohon segera diproses ya, terima kasih!`;
                    waBtn.href = `https://wa.me/6282321963638?text=${encodeURIComponent(message)}`;
                } else {
                    waBtn.classList.add('opacity-50', 'pointer-events-none');
                    waBtn.href = '#';
                }
            } catch (error) {
                handleError('Failed to recalculate cart: ' + error.message);
            }
        }
    </script>
</body>
</html>
"""

@app.route("/")
def home():
    """Main landing page endpoint fetching original Jambi menu items from SQLite database."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        menu_items = cursor.execute("SELECT * FROM menu_items WHERE is_active = 1").fetchall()
        conn.close()
        return render_template_string(HTML_TEMPLATE, menu_items=menu_items)
    except DatabaseError as e:
        logger.error(f"Error loading home page: {str(e)}")
        return jsonify({"error": "Failed to load page"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in home route: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route("/api/creators")
def creators_api():
    """Returns matching creator portfolio cards based on category tag filtering and text input values."""
    try:
        category = request.args.get('category', 'All')
        search_query = request.args.get('search', '').strip()
        
        # Validate inputs
        if category != 'All':
            category = validate_string_input(category, MAX_SEARCH_QUERY_LENGTH, "category")
        
        if search_query:
            search_query = validate_string_input(search_query, MAX_SEARCH_QUERY_LENGTH, "search")
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        sql = "SELECT * FROM creators WHERE 1=1"
        params = []
        
        if category != 'All':
            sql += " AND category = ?"
            params.append(category)
            
        if search_query:
            sql += " AND (name LIKE ? OR skills LIKE ? OR bio LIKE ?)"
            params.extend([f"%{search_query}%", f"%{search_query}%", f"%{search_query}%"])
        
        sql += " ORDER BY name ASC"
        
        creators = cursor.execute(sql, params).fetchall()
        conn.close()
        
        if not creators:
            return """
            <div class="col-span-full text-center py-12 border border-zinc-800 border-dashed rounded-xl">
                <span class="material-icons text-3xl text-zinc-600 mb-2">person_off</span>
                <p class="text-xs text-zinc-500">No Jambi creative specialists matched your search filters.</p>
            </div>
            """
        
        card_template = ""
        for creator in creators:
            # Safely escape HTML entities
            safe_name = (str(creator['name']).replace("&", "&amp;").replace("<", "&lt;")
                        .replace(">", "&gt;").replace('"', "&quot;"))
            safe_skills = (str(creator['skills']).replace("&", "&amp;").replace("<", "&lt;")
                          .replace(">", "&gt;").replace('"', "&quot;"))
            safe_bio = (str(creator['bio']).replace("&", "&amp;").replace("<", "&lt;")
                       .replace(">", "&gt;").replace('"', "&quot;"))
            safe_location = (str(creator['location']).replace("&", "&amp;").replace("<", "&lt;")
                            .replace(">", "&gt;").replace('"', "&quot;"))
            safe_badge = (str(creator['badge']).replace("&", "&amp;").replace("<", "&lt;")
                         .replace(">", "&gt;").replace('"', "&quot;"))
            
            card_template += f"""
            <div class="creator-card bg-zinc-900/40 border border-zinc-800 rounded-xl overflow-hidden group hover:border-zinc-700 transition-all">
                <div class="h-40 bg-gradient-to-tr from-orange-950/40 to-zinc-900 flex items-center justify-center relative">
                    <span class="text-xs font-bold tracking-widest uppercase bg-charcoal/80 border border-neonOrange/20 px-3 py-1 rounded text-neonOrange">{safe_badge}</span>
                </div>
                <div class="p-5">
                    <div class="flex items-center gap-2 mb-2">
                        <span class="text-[10px] bg-zinc-800 px-2 py-0.5 rounded text-zinc-300">{safe_name}</span>
                        <span class="text-[10px] bg-neonOrange/10 text-neonOrange px-2 py-0.5 rounded">Freelance</span>
                    </div>
                    <h3 class="font-bold text-base">{safe_skills}</h3>
                    <p class="text-xs text-zinc-400 mt-2 leading-relaxed">{safe_bio}</p>
                    <div class="mt-4 pt-4 border-t border-zinc-800 flex justify-between items-center">
                        <span class="text-xs font-mono text-zinc-500">{safe_location}</span>
                        <a href="https://wa.me/6282321963638?text=Halo%20Sapakata,%20saya%20tertarik%20dengan%20portofolio%20{safe_name}" target="_blank" rel="noopener noreferrer" class="text-neonOrange text-xs font-bold tracking-wider uppercase hover:underline">Connect</a>
                    </div>
                </div>
            </div>
            """
        return card_template
    
    except ValidationError as e:
        logger.warning(f"Validation error in creators_api: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except DatabaseError as e:
        logger.error(f"Database error in creators_api: {str(e)}")
        return jsonify({"error": "Failed to load creators"}), 500
    except Exception as e:
        logger.error(f"Unexpected error in creators_api: {str(e)}")
        return jsonify({"error": "An unexpected error occurred"}), 500

@app.route("/api/booking/calculate", methods=["POST"])
def calculate_booking_api():
    """Performs dynamic calculations on the backend database matching client configurations."""
    try:
        # Validate and sanitize form inputs
        space = validate_string_input(request.form.get("space", "discussion"), 20, "space")
        duration = validate_integer_input(request.form.get("duration", 2), 1, 8, "duration")
        pax = validate_integer_input(request.form.get("pax", 5), 1, 25, "pax")
        catering = validate_string_input(request.form.get("catering", "none"), 20, "catering")
        
        # Cost structures
        space_rates = {
            "discussion": 50000,
            "communal": 0,
            "private": 100000
        }
        
        catering_rates = {
            "none": 0,
            "coffee": 25000,
            "meal": 45000
        }
        
        space_label = {
            "discussion": "Group Discussion Zone",
            "communal": "Communal Work Table",
            "private": "Private Studio Lounge"
        }
        
        catering_label = {
            "none": "No Catering Package Selected",
            "coffee": "Coffee + Snack Bundle",
            "meal": "Heavy Meal + Iced Tea"
        }
        
        # Validate space and catering values
        if space not in space_rates:
            raise ValidationError("Invalid space type selected")
        if catering not in catering_rates:
            raise ValidationError("Invalid catering option selected")
        
        space_subtotal = space_rates[space] * duration
        catering_subtotal = catering_rates[catering] * pax
        grand_total = space_subtotal + catering_subtotal
        
        # Build WhatsApp URL message parameter
        wa_message = f"""Halo Sapakata Creative Hub! Saya ingin mengajukan permohonan reservasi ruang:

• Tipe Ruang: {space_label[space]}
• Durasi: {duration} Jam
• Jumlah Orang: {pax} Pax
• Paket Katering: {catering_label[catering]}

*Total Estimasi Biaya:* IDR {grand_total:,.0f}

Apakah ruang tersedia? Terima kasih!""".replace(",", ".")
        
        wa_link = f"https://wa.me/6282321963638?text={wa_message}"
        
        invoice_template = f"""
        <div>
            <h3 class="text-sm font-bold tracking-wider uppercase border-b border-zinc-800 pb-3 mb-4 text-zinc-400">Estimated Cost Invoice</h3>
            
            <div class="space-y-3 text-xs">
                <div class="flex justify-between items-center text-zinc-400">
                    <span>Space Rental Cost:</span>
                    <span class="font-mono text-white">{space_label[space]} ({duration} hr)</span>
                </div>
                <div class="flex justify-between items-center text-zinc-300 font-mono pl-3">
                    <span>↳ Subtotal:</span>
                    <span>IDR {space_subtotal:,.0f}</span>
                </div>

                <div class="flex justify-between items-center text-zinc-400 border-t border-zinc-800/60 pt-3">
                    <span>F&B Catering cost:</span>
                    <span class="font-mono text-white">{catering_label[catering]} ({pax} pax)</span>
                </div>
                <div class="flex justify-between items-center text-zinc-300 font-mono pl-3">
                    <span>↳ Subtotal:</span>
                    <span>IDR {catering_subtotal:,.0f}</span>
                </div>
            </div>
        </div>

        <div class="mt-6 pt-6 border-t border-zinc-800">
            <div class="flex justify-between items-end mb-6">
                <div>
                    <span class="text-[10px] text-zinc-500 uppercase tracking-widest font-mono">ESTIMATED TOTAL</span>
                    <h2 class="text-3xl font-black font-mono text-neonOrange tracking-tight leading-none mt-1">IDR {grand_total:,.0f}</h2>
                </div>
                <span class="text-[10px] text-zinc-500 font-mono">Python Core</span>
            </div>

            <a href="{wa_link}" target="_blank" rel="noopener noreferrer" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold tracking-widest text-xs uppercase py-4 px-6 rounded-lg flex items-center justify-center gap-2 transition-all">
                <span class="material-icons text-sm">schedule_send</span> Inquire via WhatsApp
            </a>
            <p class="text-[10px] text-zinc-500 text-center mt-3">Submitting launches a dynamic inquiry thread directly with our Jambi management node.</p>
        </div>
        """.replace(",", ".")
        
        return invoice_template
    
    except ValidationError as e:
        logger.warning(f"Validation error in booking calculation: {str(e)}")
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Error in booking calculation: {str(e)}")
        return jsonify({"error": "Failed to calculate booking"}), 500

@app.before_request
def log_request():
    """Log incoming requests for debugging."""
    logger.debug(f"{request.method} {request.path}")

@app.after_request
def set_security_headers(response):
    """Add security headers to responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    return response

if __name__ == "__main__":
    # Standard Flask local deployment parameters
    # NOTE: For production, use a WSGI server like Gunicorn
    app.run(host="127.0.0.1", port=5000, debug=False)
