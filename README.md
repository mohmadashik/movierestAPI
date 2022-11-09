This is a simple movie database REST API

Follow the procedure to use this API in your local

First download this repository and install the recommendations

pip install flask

pip install jsonify  

pip install flask_jwt_extended   -- to maintain the session usin jwt tokens  -- for more details go to https://flask-jwt-extended.readthedocs.io/en/stable/blocklist_and_token_revoking/  

pip install redis   -- to store the blocklisted tokens

pip install redis-server  -- to use redis


now we are done with all requirements so that we can proceed by running the API


python3 app.py

the site will be active you may check that at

http://127.0.0.1:8000/


Now you can use the test collections provided in the "postman test collections.json"  file to check the outcome in POSTMAN API
