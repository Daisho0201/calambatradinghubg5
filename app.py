import os
import json  # Make sure to import json for handling JSON data
from functools import wraps
from flask import Flask, jsonify, render_template, request, redirect, url_for, session, flash
from PIL import Image
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector
import MySQLdb
from mysql.connector import Error
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from dotenv import load_dotenv
import cloudinary
import cloudinary.uploader

# Load environment variables from .env file
load_dotenv()

# Configure Cloudinary with your credentials
cloudinary.config( 
    cloud_name = "devdvffal", 
    api_key = "786597521674718", 
    api_secret = "WNUK4s9g3rpgvArOZuQsFU2e9Cg"
)

# Default image URL (use a Cloudinary default image)
DEFAULT_IMAGE_URL = "https://res.cloudinary.com/devdvffal/image/upload/v1/default-item.jpg"

app = Flask(__name__)
app.secret_key = 'your_secret_key'  # Required for session management


# Set the upload folders for item grid and detail images
GRID_UPLOAD_FOLDER = 'static/uploads/grid_images'
DETAIL_UPLOAD_FOLDER = 'static/uploads/detail_images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
UPLOAD_FOLDER = 'static/uploads'


app.config['GRID_UPLOAD_FOLDER'] = GRID_UPLOAD_FOLDER
app.config['DETAIL_UPLOAD_FOLDER'] = DETAIL_UPLOAD_FOLDER
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure that the upload directories exist
os.makedirs(GRID_UPLOAD_FOLDER, exist_ok=True)
os.makedirs(DETAIL_UPLOAD_FOLDER, exist_ok=True)

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)

# Allowed file check
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database connection
def get_db_connection():
    try:
        print("Attempting database connection with SSL configuration...")
        
        connection = mysql.connector.connect(
            host='mysql-1eef0d0e-marketplace-e1a9.f.aivencloud.com',
            port=28562,
            user='avnadmin',
            password='AVNS_1z1MpJQf9fVC_t-eNwP',
            database='defaultdb',
            use_pure=True,
            ssl_disabled=False,
            ssl_verify_identity=False  # Disable SSL identity verification
        )
        print("Database connection successful!")
        return connection
    except mysql.connector.Error as err:
        print(f"Error connecting to database: {err}")
        print(f"Error type: {type(err)}")
        print(f"Error details: {str(err)}")
        raise

# Create the items table
def create_items_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(''' 
        CREATE TABLE IF NOT EXISTS items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            price DECIMAL(10, 2) NOT NULL,
            description TEXT NOT NULL,
            quality ENUM('new', 'used_like_new', 'used_good', 'used_fair') NOT NULL,
            category VARCHAR(100) NOT NULL,
            meetup_place VARCHAR(255) NOT NULL,
            seller_phone VARCHAR(15) NOT NULL,
            grid_image VARCHAR(255),
            detail_images TEXT,
            user_id INT,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    ''')
    conn.commit()
    cursor.close()
    conn.close()

# Example in-memory database (replace with a real database for production)
proofs_data = []

# Route for user information
@app.route('/user_info', methods=['GET', 'POST'])
@login_required
def user_info():
    try:
        user_id = session['user_id']
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        if request.method == 'POST':
            # Handle form submission for user info updates
            first_name = request.form['first_name']
            last_name = request.form['last_name']
            username = request.form['username']
            email = request.form['email']

            # Update user information
            cursor.execute(
                "UPDATE users SET first_name = %s, last_name = %s, username = %s, email = %s WHERE id = %s",
                (first_name, last_name, username, email, user_id)
            )
            conn.commit()

        # Fetch current user information
        cursor.execute(
            "SELECT id, first_name, last_name, username, email, profile_picture FROM users WHERE id = %s", 
            (user_id,)
        )
        user_data = cursor.fetchone()
        
        print("User Data:", user_data)

        # Fetch posted items with only the columns that exist
        cursor.execute("""
            SELECT id, title as name, price, description,
                   '/static/images/default-item.jpg' as grid_image 
            FROM items 
            WHERE seller_id = %s
        """, (user_id,))
        posted_items = cursor.fetchall()
        
        print("Posted Items:", posted_items)  # Debug: Print posted items

        cursor.close()
        conn.close()

        if not user_data:
            return redirect(url_for('login'))

        return render_template('user_info.html', user=user_data, posted_items=posted_items)

    except Exception as e:
        print(f"Error in user_info route: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return "An error occurred", 500



# User class for Flask-Login
class User(UserMixin):
    def __init__(self, id, username, email):
        self.id = id
        self.username = username
        self.email = email
        self.profile_picture = None

# Index route to display homepage
@app.route('/')
def index():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)  # Use dictionary cursor for named access
    cursor.execute("SELECT * FROM items")  # Fetch all items from the database
    items = cursor.fetchall()  # Get all items as a list of dictionaries
    cursor.close()
    conn.close()
    return render_template('homepage.html', items=items)

# Homepage route
@app.route('/homepage')
def homepage():

    # Check if 'user_id' exists in the session
    if session.get('user_id'):  # Safely access 'user_id' using get()
        return redirect(url_for('main_index'))  # Redirect to main_index if user is logged in
    else:
        return render_template('homepage.html')  # Render the login page if not logged in

# Route for searching and filtering items
@app.route('/search')
def search():
    try:
        query = request.args.get('query', '')
        print(f"Search query received: {query}")

        if not query:
            print("No query provided, redirecting to main index")
            return redirect(url_for('main_index'))

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Basic search query with only existing columns
        search_term = f"%{query}%"
        cursor.execute('''
            SELECT 
                i.id,
                i.title as name,
                i.price,
                i.image_url as grid_image,
                u.username
            FROM items i
            LEFT JOIN users u ON i.seller_id = u.id
            WHERE i.title LIKE %s 
               OR i.description LIKE %s
        ''', (search_term, search_term))
        
        results = cursor.fetchall()
        print(f"Found {len(results)} results")
        
        cursor.close()
        conn.close()
        
        return render_template('search_results.html', 
                             query=query,
                             results=results)
                             
    except Exception as e:
        print(f"Error in search route: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return "An error occurred", 500


# Route to update an item
@app.route('/update_item/<int:item_id>', methods=['GET', 'POST'])
@login_required
def update_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Fetch item details if GET request
    if request.method == 'GET':
        cursor.execute("SELECT * FROM items WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
        item = cursor.fetchone()
        cursor.close()
        conn.close()
        if item:
            return render_template('update_item.html', item=item)
        else:
            return redirect(url_for('user_info'))

    # Handle item update if POST request
    if request.method == 'POST':
        name = request.form['name']
        price = request.form['price']
        grid_image = request.form.get('grid_image')  # Update image if needed
        cursor.execute(
            "UPDATE items SET name = %s, price = %s, grid_image = %s WHERE id = %s AND user_id = %s",
            (name, price, grid_image, item_id, session['user_id'])
        )
        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('user_info'))

# Route to delete an item
@app.route('/delete_item/<int:item_id>', methods=['POST'])
@login_required
def delete_item(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM items WHERE id = %s AND user_id = %s", (item_id, session['user_id']))
    conn.commit()
    cursor.close()
    conn.close()
    return redirect(url_for('user_info'))


# Function to get user items
def get_user_items(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items WHERE user_id = %s", (user_id,))
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items

# Function to get all items
def get_all_items():
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM items")
    items = cursor.fetchall()
    cursor.close()
    conn.close()
    return items

# Route for main index
@app.route('/main_index')
@login_required  # Ensure the user is logged in
def main_index():
    try:
        print("Attempting to connect to database in main_index route...")
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        print("Executing main query...")
        cursor.execute('''
            SELECT id, 
                   title as name, 
                   price, 
                   description,
                   COALESCE(image_url, %s) as grid_image 
            FROM items 
            ORDER BY id DESC
        ''', (DEFAULT_IMAGE_URL,))
        
        all_items = cursor.fetchall()
        
        # Debug: Print each item's details
        for item in all_items:
            print(f"Item {item['id']}:")
            print(f"  Name: {item['name']}")
            print(f"  Price: {item['price']}")
            print(f"  Image URL: {item['grid_image']}")
        
        cursor.close()
        conn.close()
        
        return render_template('main_index.html', all_items=all_items)
        
    except Exception as e:
        print(f"Error in main_index route: {str(e)}")
        print(traceback.format_exc())
        return "An error occurred", 500


@app.route('/filter/<category>', methods=['GET'])
@login_required
def filter_by_category(category):
    user_id = session['user_id']
    user_items = get_user_items(user_id)
    
    if category == 'all':
        all_items = get_all_items()
    else:
        all_items = get_items_by_category(category)  # Fetch items filtered by category
    
    return render_template('main_index.html', user_items=user_items, all_items=all_items)

def get_items_by_category(category):
    connection = None  # Initialize connection variable here to avoid reference errors
    try:
        # Set up the database connection
        connection = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',  # No password
            database='marketplace'
        )

        if connection.is_connected():
            cursor = connection.cursor(dictionary=True)  # Use dictionary for easier column-to-field mapping
            query = "SELECT * FROM items WHERE category = %s"
            cursor.execute(query, (category,))
            items = cursor.fetchall()  # Fetch all items that match the category
            cursor.close()
            return items
        else:
            print("Unable to connect to the database")
            return []

    except Error as e:
        print(f"Error: {e}")
        return []

    finally:
        # Make sure the connection is only closed if it was initialized
        if connection is not None and connection.is_connected():
            connection.close()


def add_item_columns():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Check if the columns exist before adding them
        cursor.execute("SHOW COLUMNS FROM items LIKE 'meetup_place'")
        result = cursor.fetchone()
        if not result:
            cursor.execute("ALTER TABLE items ADD COLUMN meetup_place VARCHAR(255)")
            print("Added column 'meetup_place'")
        
        cursor.execute("SHOW COLUMNS FROM items LIKE 'seller_phone'")
        result = cursor.fetchone()
        if not result:
            cursor.execute("ALTER TABLE items ADD COLUMN seller_phone VARCHAR(20)")
            print("Added column 'seller_phone'")
        
        conn.commit()
        cursor.close()
        conn.close()
        
    except Exception as e:
        print(f"Error adding columns: {str(e)}")

def create_detail_images_table():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Create detail_images table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS detail_images (
                id INT AUTO_INCREMENT PRIMARY KEY,
                item_id INT NOT NULL,
                image_url VARCHAR(255) NOT NULL,
                FOREIGN KEY (item_id) REFERENCES items(id)
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Detail images table created successfully")
        
    except Exception as e:
        print(f"Error creating detail_images table: {str(e)}")

@app.route('/item/<int:item_id>')
def item_detail(item_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        print(f"Fetching details for item ID: {item_id}")
        
        # Get item details including meetup_place and seller_phone
        cursor.execute('''
            SELECT i.id,
                   i.title as name,
                   i.price,
                   i.description,
                   i.seller_id,
                   i.image_url as grid_image,
                   COALESCE(i.meetup_place, 'To be discussed') as meetup_place,
                   COALESCE(i.seller_phone, 'Contact through chat') as seller_phone,
                   u.username,
                   u.profile_picture
            FROM items i
            LEFT JOIN users u ON i.seller_id = u.id
            WHERE i.id = %s
        ''', (item_id,))
        
        item = cursor.fetchone()
        print(f"Main item data: {item}")
        
        if item is None:
            print(f"No item found with ID: {item_id}")
            return "Item not found", 404
        
        # Initialize images list with the main image
        all_images = []
        if item['grid_image']:
            all_images.append(item['grid_image'])
            print(f"Added main image: {item['grid_image']}")
        
        # Get detail images
        cursor.execute('''
            SELECT image_url
            FROM detail_images
            WHERE item_id = %s
            ORDER BY id
        ''', (item_id,))
        
        detail_images = cursor.fetchall()
        print(f"Fetched detail images: {detail_images}")
        
        # Add detail images to the list
        for img in detail_images:
            if img['image_url']:
                all_images.append(img['image_url'])
                print(f"Added detail image: {img['image_url']}")
        
        # If no images at all, use default
        if not all_images:
            all_images = [DEFAULT_IMAGE_URL]
            print("Using default image")
        
        # Store the list of images directly
        item['detail_images'] = all_images
        print(f"Final images list: {item['detail_images']}")
        
        cursor.close()
        conn.close()
        
        return render_template('item_detail.html', 
                             item=item,
                             item_quality='Used - Good')
        
    except Exception as e:
        print(f"Error in item_detail route: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return "An error occurred", 500



@app.route('/item/<int:item_id>', methods=['GET'])
def item_details(item_id):
    conn = get_db_connection()
    cursor = conn.cursor()

    # Query to get item details and username of the seller
    cursor.execute("""
        SELECT items.*, users.username
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = %s
    """, (item_id,))
    item = cursor.fetchone()

    conn.close()

    if item:
        return render_template('item_details.html', item=item)
    else:
        flash('Item not found', 'danger')
        return redirect(url_for('main_index'))


@app.route('/save_item/<int:item_id>', methods=['POST'])
def save_item(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return redirect(url_for('login'))  # Redirect if user not logged in

    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if the item is already saved
    cursor.execute("""
        SELECT 1 FROM saved_items WHERE user_id = %s AND item_id = %s
    """, (user_id, item_id))
    existing_item = cursor.fetchone()

    if existing_item:
        # Item is already saved, return an error message
        cursor.close()
        conn.close()
        return jsonify({'status': 'error', 'message': 'This item is already saved.'})

    # Insert the item into saved_items if not already saved
    cursor.execute("""
        INSERT INTO saved_items (user_id, item_id)
        VALUES (%s, %s)
    """, (user_id, item_id))
    conn.commit()
    cursor.close()
    conn.close()

    return jsonify({'status': 'success', 'message': 'Item saved successfully.'})



@app.route('/saved_items')
@login_required
def saved_items():
    try:
        user_id = session.get('user_id')
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)
        
        # Fetch saved items for the user
        cursor.execute('''
            SELECT i.id, i.title as name, i.price, i.image_url as grid_image
            FROM saved_items s
            JOIN items i ON s.item_id = i.id
            WHERE s.user_id = %s
        ''', (user_id,))
        
        saved_items = cursor.fetchall()
        print(f"Fetched saved items: {saved_items}")
        
        cursor.close()
        conn.close()
        
        return render_template('saved_items.html', saved_items=saved_items)
        
    except Exception as e:
        print(f"Error in saved_items route: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")
        return "An error occurred", 500


@app.route('/remove_saved_item/<int:item_id>', methods=['POST'])
def remove_saved_item(item_id):
    user_id = session.get('user_id')
    if not user_id:
        return jsonify({'status': 'error', 'message': 'You must be logged in to remove items.'})

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Check if the item exists
        cursor.execute("SELECT 1 FROM saved_items WHERE user_id = %s AND item_id = %s", (user_id, item_id))
        item_exists = cursor.fetchone()

        if not item_exists:
            return jsonify({'status': 'error', 'message': 'The item does not exist in your saved list.'})

        # Remove the item
        cursor.execute("DELETE FROM saved_items WHERE user_id = %s AND item_id = %s", (user_id, item_id))
        conn.commit()

        # Explicitly return success
        return jsonify({'status': 'success', 'message': 'Item removed from your saved list.'})
    except Exception as e:
        print(f"Error occurred: {e}")  # Debugging
        return jsonify({'status': 'error', 'message': 'An unexpected error occurred while removing the item.'})
    finally:
        cursor.close()
        conn.close()






@app.route('/adminresponse', methods=['GET'])
def admin_response():
    """Renders the admin page with the list of proofs."""
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT * FROM handle_request")
        columns = [column[0] for column in cursor.description]  # Get column names
        requests = [dict(zip(columns, row)) for row in cursor.fetchall()]  # Map rows to dictionaries
        
        print("Fetched data:", requests)  # Debugging line to check what data is returned
        
        return render_template('adminresponse.html', requests=requests)
    except Exception as e:
        flash(f"Error retrieving data: {e}", "danger")
        return redirect(url_for('admin_response'))
    finally:
        cursor.close()
        conn.close()





@app.route('/confirm_request/<string:reference_type>', methods=['POST'])
def confirm_request(reference_type):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update the status to 'Confirmed' in the handle_request table
        cursor.execute("UPDATE handle_request SET status = %s WHERE reference_type = %s", ('Confirmed', reference_type))
        # Log the status change in the status_history table
        cursor.execute(
            "INSERT INTO status_history (reference_type, status) VALUES (%s, %s)",
            (reference_type, 'Confirmed')
        )
        conn.commit()
        flash(f"Request with reference type {reference_type} has been confirmed.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating status: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_response'))


@app.route('/reject_request/<string:reference_type>', methods=['POST'])
def reject_request(reference_type):
    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        # Update the status to 'Rejected' in the handle_request table
        cursor.execute("UPDATE handle_request SET status = %s WHERE reference_type = %s", ('Rejected', reference_type))
        # Log the status change in the status_history table
        cursor.execute(
            "INSERT INTO status_history (reference_type, status) VALUES (%s, %s)",
            (reference_type, 'Rejected')
        )
        conn.commit()
        flash(f"Request with reference type {reference_type} has been rejected.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error updating status: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('admin_response'))








@app.route('/submit_proof', methods=['POST'])
def submit_proof():
    sender_name = request.form.get('sender_name')
    sender_number = request.form.get('sender_number')
    reference_type = request.form.get('reference_type')
    screenshot_file = request.files.get('screenshot')
    item_name = request.form.get('item_name')
    item_id = request.form.get('item_id')

    # Validate screenshot and item_name
    if not item_name:
        flash("Item name is required.", "danger")
        return redirect(url_for('item_detail', item_id=item_id))

    if not screenshot_file or screenshot_file.filename == '':
        flash("Screenshot is required. Please upload a screenshot of the payment.", "danger")
        return redirect(url_for('item_detail', item_id=item_id))

    # Process the screenshot and save it
    file_path = f"static/uploads/{screenshot_file.filename}"
    screenshot_file.save(file_path)

    # Insert proof of payment
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        query = """
        INSERT INTO handle_request (sender_name, sender_number, reference_type, screenshot, status, item_name)
        VALUES (%s, %s, %s, %s, %s, %s)
        """
        cursor.execute(query, (sender_name, sender_number, reference_type, file_path, 'Pending', item_name))
        conn.commit()
        flash("Proof of payment has been successfully submitted. Your request is now pending approval.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error while submitting proof of payment: {e}", "danger")
    finally:
        cursor.close()
        conn.close()

    return redirect(url_for('item_detail', item_id=item_id))




@app.route('/check_status')
def check_status():
    reference_type = request.args.get('referenceType')

    if not reference_type:
        return jsonify({"error": "Reference type is required."}), 400

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    # Query the database for the reference type
    cursor.execute("""
        SELECT status FROM handle_request WHERE reference_type = %s
    """, (reference_type,))
    
    record = cursor.fetchone()
    cursor.close()
    conn.close()

    if record:
        return jsonify({"status": record['status']})
    return jsonify({"error": "Reference type not found."}), 404





@app.route('/proceed_purchase/<int:item_id>', methods=['POST'])
def proceed_purchase(item_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute("""
        SELECT items.*, users.username
        FROM items
        JOIN users ON items.user_id = users.id
        WHERE items.id = %s
    """, (item_id,))
    
    item = cursor.fetchone()
    cursor.close()
    conn.close()

    if item:
        buyer_name = "John Doe"  # Replace with session/user data if available
        contact_info = "johndoe@example.com"  # Replace with session/user data if available
        
        return render_template(
            'purchasesuccess.html', 
            buyer_name=buyer_name,
            contact_info=contact_info,
            item=item
        )
    else:
        return "Item not found", 404


# Route for login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')  # Fetch email instead of username
        password = request.form.get('password')

        if not email or not password:  # Check for missing email or password
            return "Missing email or password", 400  # Return an informative error

        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        try:
            # Query to check for the user's email
            cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
            user_data = cursor.fetchone()

            # Validate user and password
            if user_data and check_password_hash(user_data['password'], password):  # Use hashed password check
                user = User(user_data['id'], user_data['username'], user_data['email'])  # Create User object
                login_user(user)  # Log in the user with Flask-Login
                session['user_id'] = user.id  # Store user ID in session
                return redirect(url_for('main_index'))  # Redirect to main_index on successful login

            return "Invalid email or password", 401  # Handle invalid login
        except Exception as e:
            return f"An error occurred: {e}", 500  # Handle unexpected errors
        finally:
            cursor.close()
            conn.close()  # Ensure the database connection is closed

    # Render the login form for GET requests
    return render_template('homepage.html')



# Route for registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        # Collect data from the form
        first_name = request.form['first_name']
        last_name = request.form['last_name']
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        confirm_password = request.form['confirm_password']

        # Validate passwords match
        if password != confirm_password:
            return "Passwords do not match. Please try again."

        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor()

        # Check if the username or email already exists
        cursor.execute("SELECT * FROM users WHERE username = %s OR email = %s", (username, email))
        if cursor.fetchone():
            return "Username or email already exists. Please try another."

        # Hash the password and insert the new user into the database
        hashed_password = generate_password_hash(password)
        cursor.execute(
            "INSERT INTO users (first_name, last_name, username, email, password) VALUES (%s, %s, %s, %s, %s)",
            (first_name, last_name, username, email, hashed_password)
        )
        conn.commit()
        cursor.close()
        conn.close()

        # Redirect to the login page upon successful registration
        return redirect(url_for('login'))

    return render_template('register.html')



# Route for logout
@app.route('/logout')
@login_required  # Ensure the user is logged in
def logout():
    logout_user()  # Log the user out
    session.pop('user_id', None)  # Remove user ID from session
    return redirect(url_for('homepage'))  # Redirect to the homepage

# User loader function for Flask-Login
@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    user_data = cursor.fetchone()
    cursor.close()
    conn.close()
    if user_data:
        return User(user_data['id'], user_data['username'], user_data['email'])
    return None

# Ensure to create the items table when the application starts
create_items_table()

@app.route('/post_item', methods=['GET', 'POST'])
@login_required
def post_item():
    try:
        if request.method == 'POST':
            # Get form data
            title = request.form['item_name']
            price = request.form['item_price']
            description = request.form['item_desc']
            meetup_place = request.form.get('meetup_place', 'To be discussed')  # New field
            seller_phone = request.form.get('seller_phone', 'Contact through chat')  # New field
            seller_id = session.get('user_id')
            
            # Handle main image upload
            image_url = DEFAULT_IMAGE_URL
            if 'grid_image' in request.files:
                grid_image = request.files['grid_image']
                if grid_image and grid_image.filename != '':
                    try:
                        upload_result = cloudinary.uploader.upload(grid_image)
                        image_url = upload_result['secure_url']
                        print(f"Main image uploaded: {image_url}")
                    except Exception as e:
                        print(f"Error uploading main image: {str(e)}")

            conn = get_db_connection()
            cursor = conn.cursor()

            # Insert the main item with meetup_place and seller_phone
            cursor.execute('''
                INSERT INTO items (title, price, description, seller_id, image_url, meetup_place, seller_phone)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            ''', (title, price, description, seller_id, image_url, meetup_place, seller_phone))
            
            item_id = cursor.lastrowid
            print(f"New item inserted with ID: {item_id}")

            # Handle additional images
            if 'detail_images' in request.files:
                detail_files = request.files.getlist('detail_images')
                for detail_image in detail_files:
                    if detail_image and detail_image.filename != '':
                        try:
                            upload_result = cloudinary.uploader.upload(detail_image)
                            detail_url = upload_result['secure_url']
                            print(f"Detail image uploaded: {detail_url}")
                            
                            # Insert into detail_images table
                            cursor.execute('''
                                INSERT INTO detail_images (item_id, image_url)
                                VALUES (%s, %s)
                            ''', (item_id, detail_url))
                            
                        except Exception as e:
                            print(f"Error uploading detail image: {str(e)}")

            conn.commit()
            cursor.close()
            conn.close()

            return redirect(url_for('main_index'))

        return render_template('post_item.html')

    except Exception as e:
        print(f"Error in post_item route: {str(e)}")
        print(traceback.format_exc())
        return "An error occurred", 500

# Add this new route to handle profile picture updates
@app.route('/update_profile_picture', methods=['POST'])
@login_required
def update_profile_picture():
    if 'profile_picture' not in request.files:
        return jsonify({'success': False, 'error': 'No file uploaded'})
    
    file = request.files['profile_picture']
    if file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})

    if file and allowed_file(file.filename):
        try:
            # Upload to Cloudinary with specific options
            upload_result = cloudinary.uploader.upload(
                file,
                folder="profile_pictures",  # Store in a specific folder
                transformation=[
                    {'width': 300, 'height': 300, 'crop': 'fill'},  # Resize and crop to square
                    {'quality': 'auto:good'}  # Optimize quality
                ]
            )
            
            # Update database with the new profile picture URL
            conn = get_db_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "UPDATE users SET profile_picture = %s WHERE id = %s",
                (upload_result['secure_url'], session['user_id'])
            )
            
            conn.commit()
            cursor.close()
            conn.close()
            
            # Return the new profile picture URL
            return jsonify({
                'success': True,
                'profile_picture_url': upload_result['secure_url']
            })
            
        except Exception as e:
            print(f"Error uploading profile picture: {str(e)}")  # Debug log
            return jsonify({'success': False, 'error': str(e)})
    
    return jsonify({'success': False, 'error': 'Invalid file type'})

# Add this function to create/update the users table
def update_users_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Add profile_picture column if it doesn't exist
        cursor.execute("""
            ALTER TABLE users 
            ADD COLUMN IF NOT EXISTS profile_picture VARCHAR(255)
        """)
        conn.commit()
    except Exception as e:
        print(f"Error updating users table: {e}")
    finally:
        cursor.close()
        conn.close()

# Call this function when your app starts
# Add this near the bottom of your file, before the if __name__ == '__main__': line
update_users_table()

# Add this function to create necessary tables if they don't exist
def create_detail_images_table():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Create detail_images table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS detail_images (
            id INT AUTO_INCREMENT PRIMARY KEY,
            item_id INT NOT NULL,
            image_url VARCHAR(255) NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items(id)
        )
    ''')
    
    # Add meetup_place and seller_phone columns to items table if they don't exist
    try:
        cursor.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS meetup_place VARCHAR(255)")
        cursor.execute("ALTER TABLE items ADD COLUMN IF NOT EXISTS seller_phone VARCHAR(20)")
    except Exception as e:
        print(f"Note: {e}")
    
    conn.commit()
    cursor.close()
    conn.close()

# Call this when the app starts
create_detail_images_table()


if __name__ == '__main__':
    app.run(debug=True)  # Start the Flask application