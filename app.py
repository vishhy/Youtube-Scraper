from pytube import YouTube, Channel
from youtube_comment_scraper_python import youtube
from youtube_video_scraping import youtube
import pandas as pd
from sqlalchemy import create_engine
import pymongo as pm
import json
import mysql.connector as connector
import base64
from flask import Flask, request, jsonify, render_template
from flask_cors import cross_origin
import boto3
import requests
import os
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive
from decouple import config


Mongo_User = config('mongo_user')
Mongo_Passwd = config('mongo_psswd')
AWS_ACCESS_KEY = config('aws_keyid')
AWS_SECRET_KEY = config('aws_secretkey')
YT_folderid = config('yt_folderid')

gauth = GoogleAuth()
drive = GoogleDrive(gauth)

connection_sql = connector.connect(host='localhost', user='root', password='1234', auth_plugin='mysql_native_password')
cursor = connection_sql.cursor()

connection_mongo = pm.MongoClient(
    "mongodb+srv://vishwas_new:kalwogG8-4@cluster-vishwas.v3i9doq.mongodb.net/?retryWrites=true&w"
    "=majority")
db = connection_mongo.test

df_sql = pd.DataFrame(
    {'ytuber_name': [], 'video_title': [], 'video_link': [], 'likes': [], 'comments': [], 'thumbnail_url': []})
df_mongo = pd.DataFrame({'ytuber_name': [], 'video_title': [], 'comment_user': [], 'comment': [], 'thumb_b64': []})

paths = {'1': "https://www.youtube.com/user/krishnaik06/videos",
         '2': "https://www.youtube.com/c/HiteshChoudharydotcom/videos",
         '3': "https://www.youtube.com/c/Telusko/videos",
         '4': "https://www.youtube.com/user/saurabhexponent1/videos"
         }

app = Flask(__name__)


@app.route('/', methods=['GET'])  # route to display the home page
@cross_origin()
def homePage():
    return render_template("index.html")


@app.route('/ytube', methods=['POST', 'GET'])  # route to show the review comments in a web UI
@cross_origin()
def video_details():
    if request.method == 'POST':
        key_no = str(request.form['ytuber'])
        no_of_vids = int(request.form['vids_no'])
        if key_no in paths.keys():
            path = paths[key_no]
            c = Channel(path)
            vid_urls = c.video_urls
            try:
                vid_urls = list(vid_urls[0:no_of_vids])
            except:
                vid_urls = []
                app.logger.warning("Video Urls list is empty")

            for i in vid_urls:
                # Downloading Videos
                y = YouTube(i)
                vid_down = y.streams.first()
                try:
                    vid_down.download(r'F:\FSDS\Projects\Scraper\YT Scraper_ver2\Videos')
                except:
                    pass

                # Extracting Video Details
                try:
                    vid_title = y.title
                except:
                    vid_title = 'N/A'
                try:
                    vid_thumb_url = y.thumbnail_url
                except:
                    vid_thumb_url = 'N/A'
                try:
                    vid_ytname = y.author
                except:
                    vid_ytname = 'N/A'
                try:
                    vid_url = i
                except:
                    vid_url = 'N/A'

                # Converting Video Thumbnail to base64 encoding
                try:
                    vid_thumb_b64 = base64.b64encode(requests.get(vid_thumb_url).content)
                    vid_thumb_b64 = str(vid_thumb_b64)
                except:
                    vid_thumb_b64 = 'Unable to Encode'

                # Extracting no. of likes and comments for videos
                response = youtube.get_video_info(video_url=i)
                try:
                    vid_likes = response['body']['Likes']
                except:
                    vid_likes = 'N/A'
                try:
                    vid_comments = response['body']['Comments']
                except:
                    vid_comments = 'N/A'

                youtube.open(i)
                response1 = youtube.video_comments()
                try:
                    data = response1['body']
                except:
                    data = []

                for j in data:
                    try:
                        comment = j['Comment']
                    except:
                        comment = 'N/A'
                    try:
                        comment_user = j['user']
                    except:
                        comment_user = 'N/A'

                    df_mongo.loc[len(df_mongo.index)] = [vid_ytname, vid_title, comment_user, comment, vid_thumb_b64]

                df_sql.loc[len(df_sql.index)] = [vid_ytname, vid_title, vid_url, vid_likes, vid_comments, vid_thumb_url]

            export_vid_aws()
            pre_url = generate_presigned_url()
            pre_url = pd.Series(pre_url)
            df_sql.insert(loc=3, column='aws_s3_link', value=pre_url, allow_duplicates=True)

            for i in os.listdir(r"Videos"):
                gfile = drive.CreateFile({'parents': [{'id': YT_folderid}]})
                # Read file and set it as the content of this instance.
                gfile.SetContentFile(f"Videos/{i}")
                gfile.Upload()  # Upload the file.

            gdrive_list = []
            file_list = drive.ListFile(
                {'q': "'{}' in parents and trashed=false".format(YT_folderid)}).GetList()
            for file in file_list:
                gdrive_list.append('https://drive.google.com/file/d/%s/view?usp=sharing' % (file['id']))

            gdrive_list = pd.Series(gdrive_list)
            df_sql.insert(loc=4, column='gdrive_link', value=gdrive_list, allow_duplicates=True)

            file_handling()
            sql_upload()
            mongo_upload()
            return render_template("render.html")

        else:
            return render_template("index.html")


@app.route('/ytube/sql', methods=['GET', 'POST'])
@cross_origin()
def render_sql():
    return render_template("Results_Sql.html")


@app.route('/ytube/mongo', methods=['GET', 'POST'])
@cross_origin()
def render_mongo():
    return render_template("Results_Mongo.html")


def export_vid_aws():
    directory = r"F:\FSDS\Projects\Scraper\YT Scraper_ver2\Videos"

    for filename in os.listdir(directory):
        f = os.path.join(directory, filename)
        if os.path.isfile(f):
            s3 = boto3.client("s3")
            s3.upload_file(
                Filename=f,
                Bucket="vishwas-bucket",
                Key=filename,
            )


def generate_presigned_url(expiry=3600):
    pre_url = []
    client = boto3.client("s3", region_name="us-east-2",
                          aws_access_key_id=AWS_ACCESS_KEY,
                          aws_secret_access_key=AWS_SECRET_KEY)
    resource = boto3.resource('s3')
    my_bucket = resource.Bucket('vishwas-bucket')
    buck_obj = my_bucket.objects.all()

    for i in buck_obj:
        if i.key in os.listdir(r"F:\FSDS\Projects\Scraper\YT Scraper_ver2\Videos"):
            try:
                response = client.generate_presigned_url('get_object',
                                                         Params={'Bucket': 'vishwas-bucket', 'Key': i.key},
                                                         ExpiresIn=expiry)
                pre_url.append(str(response))
            except:
                pre_url.append('No Url')

    return pre_url


# Enter the channel name of the youtuber
df_sql = df_sql.fillna('N/A')
df_mongo = df_mongo.fillna('N/A')


def file_handling():
    html_string = '''
    <html>
      <head><title>Youtube Scraping Results</title></head>
      <link rel="stylesheet" type="text/css" href="static/table_style.css"/>
      <body>
        {table}
      </body>
    </html>
    '''

    # OUTPUT AN HTML FILE
    with open(r"templates/Results_Sql.html", 'w', encoding='utf-8') as f:
        f.write(html_string.format(table=df_sql.to_html(justify='left')))

    # OUTPUT AN HTML FILE
    with open(r"templates/Results_Mongo.html", 'w', encoding='utf-8') as f:
        f.write(html_string.format(table=df_mongo.to_html(justify='left')))


def sql_upload():
    try:
        engine = create_engine('mysql+mysqlconnector://' + 'root' + ':' + '1234' + '@' + 'localhost' ':' + '3306',
                               echo=False)
        df_sql.to_sql(name='data_mysql', schema='ytube_scrape', con=engine, if_exists='append', index=False)
    except:
        pass


def mongo_upload():
    database = connection_mongo['ytube_scrape']
    collection = database['data_mongoDB']

    df_mongo_json = df_mongo.to_json(r"F:\FSDS\Projects\Scraper\YT Scraper_ver2\mongo_json.json", orient='records')
    try:
        with open("mongo_json.json") as json_file:
            file_data = json.load(json_file)
    except:
        file_data = {'data': 'no data'}
    # Inserting data in mongo db
    if isinstance(file_data, list):
        try:
            collection.insert_many(file_data)
        except:
            file_data = {'data': 'no data'}
            collection.insert_one(file_data)
    else:
        try:
            collection.insert_one(file_data)
        except:
            file_data = {'data': 'no data'}
            collection.insert_one(file_data)


if __name__ == "__main__":
    app.run(host='127.0.0.1', port=8001, debug=True)
    # app.run(debug=True)
