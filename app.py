from flask import Flask, jsonify, make_response, request,Response
from flask_jwt_extended import (
    JWTManager,
    jwt_required,
    create_access_token,
    get_jwt,
    get_jwt_identity                 #to get the email id of user from current jwt token
    )
import redis
import re
from datetime import timedelta,datetime
from bson.objectid import ObjectId

from pymongo import MongoClient

ACCESS_EXPIRES = timedelta(hours=10)

app = Flask(__name__)
app.config['SECRET_KEY'] ='thisissecretkey'
app.config['JWT_blocklist_ENABLED'] = True
app.config['JWT_blocklist_TOKEN_CHECKS'] = ['access', 'refresh']
app.config["JWT_ACCESS_TOKEN_EXPIRES"] = ACCESS_EXPIRES

jwt = JWTManager(app)

client = MongoClient("mongodb://localhost:27017/")
db = client['moviesdb']
user_col = db['user']
movie_col = db['movie']

jwt_redis_blocklist = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(jti)
    return token_in_redis is not None

@app.route("/")
def home():
    return jsonify({"Status":'the site is active'}),200

@app.route('/register',methods=['POST'])
def register():
    status = ''
    if 'username' and 'password' and 'email' in request.json :
        username = request.json['username']
        password = request.json['password']
        email = request.json['email']
        user_query = {'username':username}
        check_user  = user_col.find_one(user_query)
        if check_user!=None and (check_user['email']==email or check_user['username']==username):
            status = 'Account already exists !'
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            status = 'Invalid email address !'
        elif not re.match(r'[A-Za-z0-9]+', username):
            status = 'Username must contain only characters and numbers !'
        elif not username or not password or not email:
            status = 'Please fill out the form !'
            return
        else:
            user_col.insert_one({'username':username,'password':password,'email':email,'genre':None})
            status = 'You have successfully registered !'
    elif request.method == 'POST':
        status = 'Please fill out the form !'
    return jsonify({"status": status})

@app.route('/login')
def login():
    if 'email' in request.json and 'password' in request.json:
        email = request.json['email']
        password = request.json['password']
        check_user = user_col.find_one({'email':email})
        if check_user and check_user['password']==password:
            output = {
                'Status'    : 'access token created',
                'access_token': create_access_token(identity=email)
            }
            return jsonify(output), 200
        else:
            output = {'Error':'wrong credentials'}
            return jsonify(output),400
    return make_response('could not verify',  401, {'Authentication': '"login required"'})

@app.route('/profile')
@jwt_required()
def profile():
    return jsonify({'Status':'profile page is active'})

# Endpoint for revoking the current users access token
@app.route('/logout', methods=['DELETE'])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_redis_blocklist.set(jti, "", ex=ACCESS_EXPIRES)
    return jsonify({'status':'Access token revoked'})

@app.route('/addmovie',methods=['POST'])
@jwt_required()
def addmovie():
    if 'movie' and 'date' and 'genre' in request.json:
        movie = request.json['movie']
        date  = request.json['date']
        genre = request.json['genre']
        check_movie = movie_col.find_one({'movie':movie})
        inserted_id = movie_col.insert_one({'movie':movie,'date':date,'genre':genre,'upvotes':0,'downvotes':0 }).inserted_id
        output = {
            'status': "movie added successfully",
            'inserted_id' : str(inserted_id)
          }
    else:
        output = {'status' : "please fill out the form"}
    return jsonify(output)

@app.route('/viewmovies')
def movielist():
    documents = movie_col.find()
    output = [{item: data[item] for item in data if item!='_id'} for data in documents]
    return jsonify(output)

@app.route('/editmovie/<movieid>/',methods=['PUT'])
@jwt_required()
def editmovie(movieid):
    filt = {'_id':ObjectId(movieid)}
    updated_data = {"$set":request.json}
    response = movie_col.update_one(filt,updated_data)
    output = {'Status':'Succesfully Updated' if response.modified_count>0 else "Nothing was updated."}
    return output

@app.route('/deletemovie/<movieid>/',methods=['DELETE'])
@jwt_required()
def deletemovie(movieid):
    response = movie_col.delete_one({"_id":ObjectId(movieid)})
    output = {'Status': 'Successfully Deleted' if response.deleted_count > 0 else "Document not found."}
    return output

@app.route('/setgenre',methods=['PUT'])
@jwt_required()
def setgenre():
    filt = {"email":get_jwt_identity()}
    updated_data = {"$set":request.json}
    response = user_col.update_one(filt,updated_data)
    output = {'Status':'Succesfully Updated The Genre' if response.modified_count>0 else"Nothing was updated."}
    return output

@app.route('/recommendations')
@jwt_required()
def getrecommendations():
    email = get_jwt_identity()
    fav_genre = user_col.find_one({"email":email})['genre']
    documents = movie_col.find({"genre":fav_genre})
    output = [{item: data[item] for item in data if item!='_id'} for data in documents]
    return jsonify(output)

@app.route('/sortmovies')
def sortmovies():
    status = ''
    sorting_key = request.json['sorting_key']
    order = 'desc' if 'order' not in request.json else request.json['order']
    if sorting_key =='date':
        movies = movie_col.find()
        movies = list(movies)
        for movie in movies:
            movie['date'] = datetime.strptime(movie['date'],"%d-%m-%Y").date()
        sorted_movies=sorted(movies,key=lambda i:i['date'])
        output = [{item:data[item]for item in data if item!='_id'}for data in sorted_movies]
    elif sorting_key=='upvotes':
        sorted_movies = movie_col.find().sort("upvotes",-1)
    elif sorting_key =='downvotes':
        sorted_movies = movie_col.find().sort("downvotes",-1)
    else:
        status = "you must give a valid sorting key"
        return jsonify({"status":status})
    output = [{item: data[item] for item in data if item!='_id'} for data in sorted_movies]
    output = output if order=="desc" else output[-1::-1]
    return jsonify(output)

@app.route('/voting/<movieid>/',methods=['PUT'])
@jwt_required()
def voting(movieid):
    output = { 'status':'nothing happened' }
    new_vote = request.json['vote']
    current_user_email = get_jwt_identity()
    current_user_id   = user_col.find_one({"email":current_user_email})['_id']
    movieid = ObjectId(movieid)
    current_movie = movie_col.find_one(movieid)
    old_upvotes,old_downvotes = current_movie['upvotes'],current_movie['downvotes']
    new_upvotes = old_upvotes
    new_downvotes = old_downvotes
    if not str(current_user_id) in current_movie:
        if new_vote ==1:
            new_upvotes+=1
        else:
            new_downvotes+=1
    else:
        user_old_vote = current_movie[str(current_user_id)]
        if user_old_vote != new_vote:
            if new_vote ==1:
                new_upvotes +=1
                new_downvotes-=1
            else:
                new_downvotes +=1
                new_upvotes -=1
    filt = {"_id":movieid}
    updated_data = {"$set":{str(current_user_id):new_vote,"upvotes":new_upvotes,"downvotes":new_downvotes}}
    response = movie_col.update_one(filt,updated_data)
    output = { "status":"voted successfully"}
    return jsonify(output)

if __name__=='__main__':
    # pdb.set_trace()
    app.run(debug=True,port=8000)
