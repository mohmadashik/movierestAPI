from flask import Flask, jsonify, make_response, request,Response
from flask_jwt_extended import (
    JWTManager,
    jwt_required,
    create_access_token,
    get_jwt
    )
import pdb
import redis
import re
from datetime import timedelta,datetime

from pymongo import MongoClient

ACCESS_EXPIRES = timedelta(hours=4)

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
interest_col = db['user_interest']


jwt_redis_blocklist = redis.StrictRedis(
    host="localhost", port=6379, db=0, decode_responses=True
)

@jwt.token_in_blocklist_loader
def check_if_token_is_revoked(jwt_header, jwt_payload: dict):
    jti = jwt_payload["jti"]
    token_in_redis = jwt_redis_blocklist.get(jti)
    return token_in_redis is not None

@app.route('/register',methods=['GET','POST'])
def register():
    status = ''
    if request.method == 'POST' and 'username' in request.json and 'password' in request.json and 'email' in request.json :
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

@app.route('/login', methods=['POST'])
def login():
    # pdb.set_trace()
    if request.method=="POST" and 'username' in request.json and 'password' in request.json:
        username = request.json['username']
        password = request.json['password']
        check_user = user_col.find_one({'username':username})
        if check_user and check_user['password']==password:
            output = {
                'Status'    : 'access token created',
                'access_token': create_access_token(identity=username)
            }
            return jsonify(output), 200
        else:
            output = {'Error':'wrong credentials'}
            return jsonify(output),400
    return make_response('could not verify',  401, {'Authentication': '"login required"'})

@app.route('/profile',methods=['GET'])
@jwt_required()
def profile():
    return jsonify({'Status':'profile page is active'})


# Endpoint for revoking the current users access token
@app.route('/logout', methods=['DELETE'])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    jwt_redis_blocklist.set(jti, "", ex=ACCESS_EXPIRES)
    return jsonify(status="Access token revoked")


@app.route("/")
def home():
    return jsonify({"Status":'the site is active'}),200

@app.route('/addmovie',methods=['POST'])
@jwt_required()
def addmovie():
    status=''
    if request.method == 'POST' and 'name' in request.json and 'releasedate' in request.json and 'genre' in request.json:
        name = request.json['name']
        releasedate = request.json['releasedate']
        genre = request.json['genre']
        review = request.json['review']
        check_movie = movie_col.find_one({'name':name})
        # pdb.set_trace()
        if check_movie!=None and check_movie['name']==name:
            status = "movie already exists"
        elif not name or not releasedate or not genre:
            status = "please fill out the form"
        else:
            movie_col.insert_one({'name':name,'releasedate':releasedate,'genre':genre,'upvotes':0,'downvotes':0,'review':review})
            status = "movie added successfully"
    elif request.method =="POST":
        status = "please fill out the form"
    return jsonify({"status":status})

@app.route('/viewmovies',methods=['GET'])
# @jwt_required()
def movielist():
    documents = movie_col.find()
    output = [{item: data[item] for item in data if item!='_id'} for data in documents]
    return jsonify(output)

@app.route('/editmovie',methods=['PUT'])
@jwt_required()
def editmovie():
    data = request.json
    filt = data['Filter']
    updated_data = {"$set":data['DataToBeUpdated']}
    response = movie_col.update_one(filt,updated_data)
    output = {'Status':'Succesfully Updated' if response.modified_count>0 else"Nothing was updated."}
    return output

@app.route('/deletemovie',methods=['DELETE'])
@jwt_required()
def deletemovie():
    filt = request.json['Filter']
    response = movie_col.delete_one(filt)
    output = {'Status': 'Successfully Deleted' if response.deleted_count > 0 else "Document not found."}
    return output

@app.route('/setgenre',methods=['PUT'])
@jwt_required()
def setgenre():
    data = request.json
    filt = request.json['Filter']
    updated_data = {"$set":data['DataToBeUpdated']}
    response = user_col.update_one(filt,updated_data)
    output = {'Status':'Succesfully Updated The Genre' if response.modified_count>0 else"Nothing was updated."}
    return output
@app.route('/voting',methods=['PUT'])
@jwt_required()
def voting():
    # pdb.set_trace()
    data = request.json
    username = data['username']
    moviename = data['name']
    vote = data['vote']
    check_user = interest_col.find_one({'username':username})
    if check_user!=None:
        old_vote = check_user['votes'][moviename] if moviename in check_user['votes'] else None
        is_old_movie = True if moviename in check_user['votes'] else False
        if is_old_movie and vote == old_vote:
            status = "you have given the same vote already"
        else:
            if vote==1:
                if is_old_movie:
                    new_upvotes = movie_col.find_one({'name':moviename})['upvotes']+1
                    new_downvotes = movie_col.find_one({'name':moviename})['downvotes']-1
                else:
                    new_upvotes =  movie_col.find_one({'name':moviename})['upvotes']+1
                    new_downvotes = movie_col.find_one({'name':moviename})['downvotes']
                interest_query = {'votes.'+moviename:1}
                interest_update = {"$set":interest_query}
                response1 = interest_col.update_one({'username':username},interest_update)
                movie_query ={
                'upvotes':new_upvotes,
                'downvotes':new_downvotes
                }
                movie_update = {"$set":movie_query}
                response2 = movie_col.update_one({"name":moviename},movie_update)
                status = "upvoted successfully"
            else:
                if is_old_movie:
                    new_upvotes = movie_col.find_one({'name':moviename})['upvotes']-1
                    new_downvotes = movie_col.find_one({'name':moviename})['downvotes']+1
                else:
                    new_upvotes = movie_col.find_one({'name':moviename})['upvotes']
                    new_downvotes = movie_col.find_one({'name':moviename})['downvotes']+1
                interest_query = {'votes.'+moviename:-1}
                interest_update = {"$set":interest_query}
                response1 = interest_col.update_one({'username':username},interest_update)
                movie_query ={
                'upvotes':new_upvotes,
                'downvotes':new_downvotes
                }
                movie_update = {"$set":movie_query}
                response2 = movie_col.update_one({"name":moviename},movie_update)
                status = "downvoted successfully"
    else:
        interest_query = {'username':username,'votes':{moviename:0}}
        interest_col.insert_one(interest_query)
        if vote==1:
            new_upvotes = movie_col.find_one({'name':moviename})['upvotes']+1
            interest_query = {'votes.'+moviename:1}
            interest_update = {"$set":interest_query}
            response1 = interest_col.update_one({'username':username},interest_update)
            movie_query ={
            'upvotes':new_upvotes
            }
            movie_update = {"$set":movie_query}
            response2 = movie_col.update_one({"name":moviename},movie_update)
            status = "upvoted successfully"
        else:
            new_downvotes = movie_col.find_one({'name':moviename})['downvotes']+1
            interest_query = {'votes.'+moviename:-1}
            interest_update = {"$set":interest_query}
            response1 = interest_col.update_one({'username':username},interest_update)
            movie_query ={
            'downvotes':new_downvotes
            }
            movie_update = {"$set":movie_query}
            response2 = movie_col.update_one({"name":moviename},movie_update)
            status = "downvoted successfully"
    return {'status':status}

@app.route('/recommendations',methods=['GET'])
@jwt_required()
def getrecommendations():
    username = request.json['username']
    fav_genre = user_col.find_one({"username":username})['genre']
    documents = movie_col.find({"genre":fav_genre})
    output = [{item: data[item] for item in data if item!='_id'} for data in documents]
    return jsonify(output)

@app.route('/listmovies')
def sortmovies():
    status = ''
    sorting_key = request.json['sorting_key']
    if sorting_key =='releasedate':
        movies = movie_col.find()
        movies = list(movies)
        for movie in movies:
            movie['releasedate'] = datetime.strptime(movie['releasedate'],"%d-%m-%Y").date()
        sorted_movies=sorted(movies,key=lambda i:i['releasedate'])
        output = [{item:data[item]for item in data if item!='_id'}for data in sorted_movies]
    elif sorting_key=='upvotes':
        sorted_movies = movie_col.find().sort("upvotes",-1)
    elif sorting_key =='downvotes':
        sorted_movies = movie_col.find().sort("downvotes",-1)
    else:
        status = "you must give a valid sorting key"
        return jsonify({"status":status})
    output = [{item: data[item] for item in data if item!='_id'} for data in sorted_movies]
    return jsonify(output)


if __name__=='__main__':
    # pdb.set_trace()
    app.run(debug=True,port=8000)
