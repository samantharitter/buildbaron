"""
Routes and views for the flask application.
"""
import json

from datetime import datetime
from flask import render_template, g
from www import app

@app.route('/')
@app.route('/home')
def home():
    """Renders the home page."""
    
       
    with open("d:\\buildbaron\\failed_tests.json", "rb") as sjh:
        failed_tests = json.load(sjh)

    return render_template(
        'index.html',
        title='Home Page',
        year=datetime.now().year
        #,failed_tests=g.get("failed_tests", None)
        ,failed_tests=failed_tests
    )

@app.route('/contact')
def contact():
    """Renders the contact page."""
    return render_template(
        'contact.html',
        title='Contact',
        year=datetime.now().year,
        message='Your contact page.'
    )

@app.route('/about')
def about():
    """Renders the about page."""
    return render_template(
        'about.html',
        title='About',
        year=datetime.now().year,
        message='Your application description page.'
    )
