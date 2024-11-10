from flask import render_template
from flask_wtf import FlaskForm
from flask import Flask, request, redirect, url_for, Response,jsonify,session
from wtforms import StringField, PasswordField, SubmitField,SelectField
from wtforms.validators import DataRequired
import traceback
from psycopg2 import connect
from psycopg2 import sql  
import os
import logging 



app=Flask(__name__)
app.config['SECRET_KEY'] = '20241030'
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class SearchForm(FlaskForm):
    choice1 = SelectField('选择图书馆', choices=[('南校图书馆', '南校图书馆'), ('东校图书馆', '东校图书馆')],validators=[DataRequired()])
    choice2= SelectField('选择楼层', choices=[('一楼', '一楼'), ('二楼', '二楼')],validators=[DataRequired()])
    choice3= SelectField('选择时间段', choices=[('8:00-10:00', '8:00-10:00'), ('10:00-12:00', '10:00-12:00')],validators=[DataRequired()])
    choice4=StringField('座位号')#没有验证器可以为空，为空时默认全部
    submit = SubmitField('Search')

class RegisterForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    confirm_password= PasswordField('Confirm password', validators=[DataRequired()])
    submit = SubmitField('Register')


def create_conn():
    """get connection from envrionment variable by the conn factory

    Returns:
        [type]: the psycopg2's connection object
    """
    env = os.environ
    params = {
        'database': env.get('OG_DATABASE', 'db_school'),
        'user': env.get('OG_USER', 'testuser'),
        'password': env.get('OG_PASSWORD', 'Dxq@719171'),
        'host': env.get('OG_HOST', '192.168.91.40'),
        'port': env.get('OG_PORT', 7654),
        'client_encoding':('UTF-8')  #要加这个不然会报错
    }
    conn = connect(**params)
    return conn


@app.route("/login",methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        #处理post请求，填完表单提交
        #查看账号密码是否在数据库中
        cnn=create_conn()
        cursor=cnn.cursor()
        # 获取表单数据  
        username = form.username.data  
        password = form.password.data  

        # 构建参数化查询  
        query = sql.SQL("SELECT * FROM book_eg.user WHERE username = %s AND password = %s")  
        params = (username, password)  
    #try:
        cursor.execute(query, params)
        results=cursor.fetchall()
        if len(results)==1:
            session['username']=results[0][0] #为当前会话的用户存储id，跳转到重定向页面后也可访问当前id
            return redirect(url_for('individual_information_get'))
        else:
         return "用户名/密码不正确"
        cnn.close()
    return render_template('login.html', title='Sign In', form=form)  


@app.route('/register', methods=['GET', 'POST'])
def register():

    form = RegisterForm()
    if form.validate_on_submit():
        #处理post请求，填完表单提交
        #查看账号密码是否在数据库中
        cnn=create_conn()
        cursor=cnn.cursor()
        # 获取表单数据  
        username = form.username.data  
        password = form.password.data
        # 构建参数化查询  
        query = sql.SQL("INSERT INTO book_eg.user(username,password) VALUES (%s, %s)") 
        params = (username, password)  
    #try:
        cursor.execute(query, params)
        cnn.commit()
        cnn.close()
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)  


@app.route("/search",methods=['GET','POST'])
def search():
    if 'username' not in session:
        return redirect(url_for('login'))  # 如果未登录，则重定向到登录页面
    username = session['username']  # 从会话中获取用户ID
    form = SearchForm()
    results=[]
    if form.validate_on_submit():
        #处理post请求，填完表单提交
        #查看账号密码是否在数据库中
        cnn=create_conn()
        cursor=cnn.cursor()
        # 获取表单数据  
        libray= form.choice1.data  
        floor = form.choice2.data
        time=form.choice3.data  
        seat_id= form.choice4.data
        # 构建参数化查询  
        if seat_id=='':
            query = sql.SQL("SELECT * FROM book_eg.libary_seats WHERE libary = %s AND floor = %s AND time=%s" )  
            params = (libray, floor,time)  
        else:
            query = sql.SQL("SELECT * FROM book_eg.libary_seats WHERE libary = %s AND floor = %s AND time=%s AND seat_id=%s" )  
            params = (libray, floor,time,seat_id)  
    #try:
        cursor.execute(query, params)
        results=cursor.fetchall()
        cnn.close()
    return render_template('search.html', title='Search', form=form,results=results)  

@app.route('/book-seat', methods=['POST'])
def book_seat():
    if 'username' not in session:
        return redirect(url_for('login'))  # 如果未登录，则重定向到登录页面
    username = session['username']  # 从会话中获取用户ID
    # 从请求体中获取 JSON 数据
    data = request.get_json()
    # 提取座位号
    seat_id = data.get('seat_id')
    # 提取时间段
    time=data.get("time")
    # 检查座位是否可用，更新数据库
    cnn=create_conn()
    cursor=cnn.cursor()
    query = sql.SQL("SELECT * FROM book_eg.libary_seats WHERE seat_id=%s AND time=%s" )
    params = (seat_id,time)
    cursor.execute(query, params)
    results=cursor.fetchall()
    if results[0][3].strip()=='已定': #要去除多于的空白字符
        success = False
        error_message='座位已被预订'
    else:
        query2=sql.SQL("UPDATE book_eg.libary_seats SET status='已定' WHERE seat_id=%s AND time=%s" )
        params = (seat_id,time)   
        cursor.execute(query2, params)
        cnn.commit() #要commit，不然不会执行成功的
        query3=sql.SQL("INSERT INTO book_eg.book_history(seat_id,time,username) VALUES (%s,%s,%s)" )
        params = (seat_id,time,username)   
        cursor.execute(query3, params)
        cnn.commit() #要commit，不然不会执行成功的
        success = True  
        error_message = None  
    cnn.close()
    # 根据预订结果返回 JSON 响应
    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': error_message}), 400  # 400 表示客户端错误

            

@app.route('/individual_information', methods=['GET'])
def individual_information_get():
    if 'username' not in session:
        return redirect(url_for('login'))
    username = session['username']
    print(type(username))
    cnn=create_conn()
    cursor=cnn.cursor()
    #1. 显示个人信息
    # 构建参数化查询  
    params = (username,)#单参数要加逗号  
    query = sql.SQL("SELECT * FROM book_eg.book_history WHERE username = %s" ) 
    #try:
    cursor.execute(query, params)
    results=cursor.fetchall()
    cnn.close()
    return render_template('individual_information.html', title='Individual Information', results=results,username=username)
 
@app.route('/individual_information', methods=['POST'])
def individual_information_post():
    if 'username' not in session:
        return jsonify({'success': False, 'error': 'User not logged in'}), 401
    username = session['username']
    data = request.get_json()
    seat_id = data.get('seat_id')
    time = data.get("time")
    if not seat_id or not time:
        return jsonify({'success': False, 'error': 'Missing seat_id or time'}), 400
    cnn=create_conn()
    cursor=cnn.cursor()
    #2.取消预订
     # 从请求体中获取 JSON 数据
    data = request.get_json()
    # 提取座位号
    seat_id = data.get('seat_id')
    # 提取时间段
    time=data.get("time")   
    #2.2修改座位状态
    query2=sql.SQL("UPDATE book_eg.libary_seats SET status='空闲' WHERE seat_id=%s AND time=%s" )
    params = (seat_id,time)   
    cursor.execute(query2, params)
    cnn.commit()
    #2.3删除记录
    query3=sql.SQL("delete from book_eg.book_history where seat_id=%s and time=%s and username=%s" )
    params = (seat_id,time,username)   
    cursor.execute(query3, params)
    cnn.commit() #要commit，不然不会执行成功的
    success=True
    cnn.close()

    if success:
        return jsonify({'success': True})
    else:
        return jsonify({'success': False, 'error': 'Failed to cancel reservation'}), 500


@app.route('/exit_login', methods=['GET'])
def exit_login():
    session.pop('username')
    return redirect(url_for('login'))

if __name__=='__main__':

    #app.run()
    app.run(host='0.0.0.0', port=5000, debug=True)

