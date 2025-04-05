from flask import Flask, request
import os
import requests
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'uploads')
ALLOWED_EXTENSIONS = {'stl', 'obj'}

SHOPIFY_DOMAIN = os.getenv('SHOPIFY_STORE_DOMAIN')
SHOPIFY_TOKEN = os.getenv('SHOPIFY_ACCESS_TOKEN')

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def create_draft_order(infill_value, contact_name, contact_type, contact_string, notes):
    url = f"https://{SHOPIFY_DOMAIN}/admin/api/2023-10/graphql.json"
    headers = {
        "X-Shopify-Access-Token": SHOPIFY_TOKEN,
        "Content-Type": "application/json",
    }

    note = (f"""
            Contact name: {contact_name}\n
            {contact_type}: {contact_string}\n
            Infill: {infill_value}%\n\n
            {notes}
            """)

    query = """
    mutation draftOrderCreate($input: DraftOrderInput!) {
      draftOrderCreate(input: $input) {
        draftOrder {
          id
          name
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    variables = {
        "input": {
            "note": note,
            "tags": ["3D Print Request"],
            "lineItems": [
                {
                    "title": "Custom 3D Print (Pending Pricing)",
                    "originalUnitPrice": "0.00",
                    "quantity": 1
                }
            ]
        }
    }

    response = requests.post(url, json={"query": query, "variables": variables}, headers=headers)
    response.raise_for_status()
    data = response.json()

    print(f"[DEBUG] GraphQL Response: {data}")

    if data.get("errors"):
        raise Exception(f"GraphQL error: {data['errors']}")
    if data["data"]["draftOrderCreate"]["userErrors"]:
        raise Exception(f"User error: {data['data']['draftOrderCreate']['userErrors']}")

    draft = data["data"]["draftOrderCreate"]["draftOrder"]
    return draft

@app.route('/print-request', methods=['POST'])
def handle_print_request():
    if 'file' not in request.files:
        return 'No file part', 400

    file = request.files['file']
    infill = request.form.get('infill', 'unknown')
    name = request.form.get('name', 'N/A')
    contact_str = request.form.get('contact_str', 'N/A')
    contact_type = request.form.get('contact_type', '')
    notes = request.form.get('notes', '')

    if file.filename == '':
        return 'No selected file', 400

    if file and allowed_file(file.filename):
        draft = create_draft_order(infill, name, contact_type, contact_str, notes)
        order_name = draft['name'].lstrip('#')  # e.g. "D1001"
        new_filename = f"Order_{order_name}.{file.filename.rsplit('.', 1)[1]}"

        filename = secure_filename(new_filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        print(f"[UPLOAD] {filename} saved | Draft Order: {draft['name']}")

        return f"Upload received. Draft order created: {draft['name']}", 200

    return 'Invalid file type', 400

if __name__ == '__main__':
    # Ensure the upload folder exists
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.run(host='0.0.0.0', port=5000)