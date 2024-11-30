from flask import render_template,flash
from flask_wtf import FlaskForm
from flask import Flask, request, redirect, url_for, Response,jsonify,session
from wtforms import StringField, PasswordField, SubmitField,SelectField
from wtforms.validators import DataRequired
from psycopg2 import connect
from psycopg2 import sql,DatabaseError
import os
import config
from datetime import datetime,timedelta,time
import schedule
import time as time_module
import threading
import sys
import signal


app=Flask(__name__)
app.config['SECRET_KEY'] = '20241030'
exit_event = threading.Event()
isupdate=0 # 防止启动服务器时初始更新和定期更新重复（10：00重启服务器），若没有定期更新就是0，定期更新后变为1不需要初始更新

class LoginForm(FlaskForm):
    userid = StringField('Userid', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    role = SelectField('Role', choices=[('student', 'Student'), ('admin', 'Admin')], validators=[DataRequired()])
    submit = SubmitField('Login')


class SearchForm(FlaskForm):
    choice1= SelectField('选择楼层', choices=[(1, '一楼'), (2, '二楼')], validators=[DataRequired()])
    choice2=StringField('座位号')#没有验证器可以为空，为空时默认全部
    submit = SubmitField('Search')

#Todo:需要根据具体划分时间段修改
class AppointmentForm(FlaskForm):
    start_time = SelectField('Start Time', choices=[
        (1, '08:30 AM'),
        (2, '09:00 AM'),
        (3, '09:30 AM'),
        (4, '10:00 AM'),
        (5, '10:30 AM')

    ], validators=[DataRequired()])
    end_time = SelectField('End Time', choices=[
        (1, '08:30 AM'),
        (2, '09:00 AM'),
        (3, '09:30 AM'),
        (4, '10:00 AM'),
        (5, '10:30 AM')
    ], validators=[DataRequired()])
    submit = SubmitField('Submit Appointment')

def create_conn():
    """get connection from envrionment variable by the conn factory

    Returns:
        [type]: the psycopg2's connection object
    """
    env = os.environ
    params = {
        'database': env.get('OG_DATABASE', config.DEFAULT_DATABASE),
        'user': env.get('OG_USER', config.DEFAULT_USER),
        'password': env.get('OG_PASSWORD', config.DEFAULT_PASSWORD),
        'host': env.get('OG_HOST', config.DEFAULT_HOST),
        'port': env.get('OG_PORT', config.DEFAULT_PORT),
        'client_encoding':('UTF-8')  #要加这个不然会报错
    }
    conn = connect(**params)
    return conn

@app.route("/",methods=['GET','POST'])
@app.route("/login",methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        #处理post请求，填完表单提交
        #查看账号密码是否在数据库中
        cnn=create_conn()
        cursor=cnn.cursor()
        # 获取表单数据  
        userid = form.userid.data  
        password = form.password.data  
        user_role = form.role.data
        # 构建参数化查询 
        query = sql.SQL("SELECT * FROM administrator WHERE aid = %s AND password = %s")  
        params = (userid, password)  
        if user_role=='student':
            query = sql.SQL("SELECT * FROM STUDENTS WHERE sid = %s AND password = %s")  
            params = (userid, password) 
        try:
            cursor.execute(query, params)
            results=cursor.fetchall()
            if len(results)==1:
                session['userid']=results[0][0] #为当前会话的用户存储id，跳转到重定向页面后也可访问当前id
                session['status']=results[0][2]
                print(results[0][0],results[0][1],results[0][2],results[0][3])
                return redirect(url_for('individual_information'))
            else:
                flash('用户名/密码不正确', 'error')  # 使用flash来显示错误信息，而不是直接返回字符串
                return redirect(url_for('login'))  # 重定向回登录页面                
        except Exception as e:
        # 记录错误日志或执行其他错误处理逻辑
            print(f"An error occurred: {e}")
            flash('登录时发生错误，请稍后再试。', 'error')
            return redirect(url_for('login'))
        finally:
        # 确保数据库连接被关闭
            cursor.close()
            cnn.close()
    return render_template('login.html', title='Sign In', form=form)  


#Todo:需要根据具体划分的时间段数修改all_time_slots
#Todo:可以把它改得更优雅规范
@app.route("/search",methods=['GET','POST']) 
def search():
    if 'userid' not in session:
        return redirect(url_for('login'))  # 如果未登录，则重定向到登录页面
    userid = session['userid']  # 从会话中获取用户ID
    status = session['status'] # 从会话中获得黑名单状态
    form = SearchForm()
    pivot_table = {}
    results=[]
    if form.validate_on_submit():
        #处理post请求，填完表单提交
        #查看账号密码是否在数据库中
        cnn=create_conn()
        cursor=cnn.cursor()
        # 获取表单数据  
        floor= form.choice1.data  
        seat_id= form.choice2.data
        # 构建参数化查询  
        if seat_id=='':
            query = sql.SQL("SELECT * FROM book_slot WHERE id IN (SELECT id FROM seat_info WHERE floor = %s AND isavailable='Y')" )  
            params = ( floor,)  
        else:
            query = sql.SQL("SELECT bs.* FROM book_slot bs JOIN seat_info si ON bs.id = si.id WHERE si.id = %s AND si.floor = %s AND si.isavailable = 'Y'" )  
            params = ( seat_id,floor)  
    #try:
        cursor.execute(query, params)
        results=cursor.fetchall()
        cursor.close()
        cnn.close()
        #转换为透视表,保持time_slot的顺序都一样
        all_time_slots = [1, 2, 3,4,5]
        #
        for row in results:
            id,sid,time_slot,start_time,isreserved=row
            id = id.strip()
            if id not in pivot_table:
                pivot_table[id] = {ts: None for ts in all_time_slots}
            pivot_table[id][time_slot]=isreserved
        print(pivot_table)
        
    return render_template('search.html', title='Search', form=form,results=pivot_table)  

#Todo: 可更改最大预约限制，这里设为8*30min=4h
#Todo: 奇怪，这样得到的seat_id后面一堆空格，可能是浏览器的问题
@app.route('/book_seat', methods=['GET','POST']) #改格式
def book_seat():
    if 'userid' not in session:
        return redirect(url_for('login'))  # 如果未登录，则重定向到登录页面
    userid = session['userid']  # 从会话中获取用户ID
    status=  session['status']  # 获得黑名单状态
    if(status!=0):
     flash(f'账号处于黑名单状态，无法预约')
     return render_template('book_seat.html', form=form)

    seat_id = request.args.get('seatId')
    print(seat_id)

    form = AppointmentForm()

    if form.validate_on_submit():

        start_time = int(form.start_time.data) #start_time和end_time都是time_slot编号，int类型，具体看表单定义
        end_time = int(form.end_time.data)

        try: 
            cnn = create_conn()
            cursor = cnn.cursor()

            if start_time>=end_time:
                flash(f'时间错误，请重新检查')
                return render_template('book_seat.html', form=form) #
        
            if end_time-start_time>8:#这里可以更改最大一次预约时间限制
                flash(f'一次最大预约时间为4个小时，超过最大预约时间')
                return render_template('book_seat.html', form=form)
        
            check_record=sql.SQL('select * from signin_record where sid=%s')
            params=(userid,)
            cursor.execute(check_record,params) 
            results=cursor.fetchall()
            if len(results) > 0:
                flash(f'已存在预约记录，每个账户同时只能存在一条预约信息，请在已存在预约记录签到后重试')
                return render_template('book_seat.html', form=form)                

            for i in range(start_time,end_time):
                check_query=sql.SQL('select isreserved,start_time from book_slot where id=%s and time_slot=%s')
                params=(seat_id, i)
                cursor.execute(check_query,params)
                results=cursor.fetchall()
                
                print(i)
                print(results)

                if results[0][0]=='Y':
                    flash(f'预约时间段已被预约') 
                    return render_template('book_seat.html', form=form)
                if i==start_time:
                    start_time_real=results[0][1]

            for i in range(start_time,end_time):
                update_query=sql.SQL('update book_slot  set isreserved=%s , sid=%s where id=%s and time_slot=%s')
                params=('Y',userid,seat_id, i)
                cursor.execute(update_query,params)    
    
            insert_query=sql.SQL('insert into signin_record(id,sid,start_time,sign_in_time,isSingIn) values(%s,%s,%s,NULL,%s)')
            params=(seat_id,userid,start_time_real,'N')
            cursor.execute(insert_query,params)  
            cnn.commit()   
            return redirect(url_for('individual_information'))  # 或者重定向到另一个页面
        
        except Exception as e:
            flash(f'发生错误：{str(e)}')
            cnn.rollback()  # 如果发生异常，回滚事务
            return render_template('book_seat.html', form=form)
        finally:
            cursor.close()
            cnn.close()

    return render_template('book_seat.html', form=form)


            
@app.route('/individual_information', methods=['GET','POST'])
def individual_information():
   
    if 'userid' not in session:
        flash('You must be logged in to view your information.', 'error')
        return redirect(url_for('login'))
    userid = session['userid']

    status = session['status']
    if status==0:
        status_message="账号可用"
    else:
        status_message=f"账号锁定中，{status}天后解封"

    results=[]
    
    try:
        cnn = create_conn()
        cursor = cnn.cursor()
        
        # 构建参数化查询
        params = (userid,)  # 单参数元组需要加逗号
        query = sql.SQL("SELECT * FROM SignIn_record WHERE sid = %s")
        
        cursor.execute(query, params)
        results = cursor.fetchall()
        
        # 在这里可以添加额外的处理逻辑，比如检查 results 是否为空等
        
    except (Exception, DatabaseError) as e:  
        # 记录错误日志或执行其他错误处理逻辑
        print(f"An error occurred: {e}")
        flash('Failed to retrieve individual information. Please try again later.', 'error')

    finally:
        # 确保数据库连接被关闭，无论是否发生异常
        if cursor:
            cursor.close()
        if cnn:
            cnn.close()
    unsubscribe_message = request.args.get('unsubscribe_message', '')  # 删除键时返回消息，设置一个默认值为空字符串
    print(unsubscribe_message)
    return render_template('individual_information.html', title='Individual Information', results=results, userid=userid,status=status_message, unsubscribe_message=unsubscribe_message)

 

@app.route('/unsubscribe', methods=['GET','POST'])
def unsubscribe():
    if 'userid' not in session:
        flash('You must be logged in to view your information.', 'error')
        return redirect(url_for('login'))
    userid= session['userid']
    unsubscribe_message=''
    try:
        cnn=create_conn()
        cursor=cnn.cursor()  
        cnn.autocommit = False
        #1.删除签到记录，计算取消订阅的时间是否早于开始时间至少三十分钟，是则删除

        current_time_after_30min=datetime.now()+timedelta(minutes=30)
        deleta_query=sql.SQL("DELETE FROM SignIn_record WHERE sid=%s AND start_time >= %s" )
        params = (userid,current_time_after_30min)   
        cursor.execute(deleta_query,params)
        deleted_rows = cursor.rowcount
        cnn.commit()

        if deleted_rows==0:
            unsubscribe_message="删除失败，没有待预约记录或者超过取消预约时间(至少早于开始时间的30min)"
            print(unsubscribe_message)
            
        #2.更新座位是否预约状态
        else:
            update_query=sql.SQL("UPDATE book_slot SET sid=NULL , isreserved='Y' WHERE sid = %s" )
            params=(userid, )
            cursor.execute(update_query,params)
            cnn.commit()
            unsubscribe_message="删除成功!"
          

        
    except (Exception,DatabaseError) as error:
        # 如果发生错误，回滚事务并打印错误消息
        print(error)
        if cnn:
            cnn.rollback()
    
    finally:
        # 关闭游标和连接
        if cursor:
            cursor.close()
        if cnn:
            cnn.close()
        return redirect(url_for('individual_information',unsubscribe_message=unsubscribe_message))


            

@app.route('/exit_login', methods=['GET'])
def exit_login():
    session.pop('userid')
    session.pop('status')
    return redirect(url_for('login'))


#数据库更新函数，由于是个人pc当服务器，每次启动服务器的时候需要刷新记录时间
def start_update():
    try:
        cnn=create_conn()
        cur=cnn.cursor()
        cnn.autocommit = False
        current_time=datetime.now().time()
        #超过晚上十点更新为新的一天的记录
        if current_time>=time(22,0):
            next_day=datetime.now().date()+timedelta(days=1)
            update_book_slot_query = sql.SQL("""
                UPDATE book_slot
                SET start_time = {next_day} + (start_time - date_trunc('day', start_time))::interval
        """).format(next_day=sql.Literal(next_day))
            
            update_signin_query = sql.SQL("""
                UPDATE signin_record
                SET start_time = {next_day} + (start_time - date_trunc('day', start_time))::interval
        """).format(next_day=sql.Literal(next_day))
            
        #否则更新为当天的记录
        else:
            update_book_slot_query = sql.SQL("""
            UPDATE book_slot
            SET start_time = CURRENT_DATE + (start_time - date_trunc('day', start_time))::interval
        """)
            update_signin_query = sql.SQL("""
    UPDATE signin_record
    SET start_time = current_date + (start_time AT TIME ZONE 'UTC' - date_trunc('day', start_time AT TIME ZONE 'UTC'))::interval
""")
        cur.execute(update_book_slot_query)
        cur.execute(update_signin_query)
        cnn.commit()

    except (Exception,DatabaseError) as error:
        # 如果发生错误，回滚事务并打印错误消息
        print(error)
        if cnn:
            cnn.rollback()
    
    finally:
        # 关闭游标和连接
        if cur:
            cur.close()
        if cnn:
            cnn.close()

def everyday_update():
    isupdate=1  
    try:
        cnn=create_conn()
        #关闭事务的自动提交
        cnn.autocommit = False
        cur=cnn.cursor()
        next_day=datetime.now().date()+timedelta(days=1)
        #刷新预约段时间和预约状态为'N',清空预约学生id
        update_book_slot_query = sql.SQL("""
                UPDATE book_slot
                SET start_time = {next_day} + (start_time - date_trunc('day', start_time))::interval , isreserved='N' , sid=NULL
        """).format(next_day=sql.Literal(next_day))

        #将当天未签到的学生或者未按时签到签到失败的学生加入黑名单（就是签到记录里面存留的表项对应的id）
        update_blacklisted_students = sql.SQL("""
            UPDATE STUDENTS
            SET status = 3
                WHERE sid IN (
                 SELECT sid
                FROM signin_record
             )
            """)
        #更新加入黑名单学生的状态倒计时-1
        update_student=sql.SQL("""
            UPDATE STUDENTS
             SET status = status - 1
            WHERE status <> 0
        """)
        #清除当天的所有签到记录
        update_signin_query = sql.SQL("""
                DELETE FROM signin_record
        """)
        cur.execute(update_book_slot_query)
        cur.execute(update_blacklisted_students)
        cur.execute(update_student)
        cur.execute(update_signin_query)
        cnn.commit()

    except (Exception,DatabaseError) as error:
        # 如果发生错误，回滚事务并打印错误消息
        print(error)
        if cnn:
            cnn.rollback() 
    finally:
        # 关闭游标和连接
        if cur:
            cur.close()
        if cnn:
            cnn.close()

#Todo:多线程跑起来终止时还是会有无伤大雅的报错，可改
def run_schedule():
    while not exit_event.is_set():
        schedule.run_pending()
        time_module.sleep(1)

def shutdown(sig, frame):
    # 设置退出事件
    exit_event.set()
    # 等待定时线程结束
    schedule_thread.join()
    sys.exit(0) 

if __name__=='__main__':

    #app.run()
    # 创建每天定时任务，10点更新时间，中断程序要等到10：01不然报错
    schedule.every().day.at("14:43").do(everyday_update)
    
    # 开启定时循环的线程
    schedule_thread = threading.Thread(target=run_schedule)
    
    signal.signal(signal.SIGINT, shutdown)
    
    schedule_thread.start()
    if isupdate==0:
        start_update()   

    app.run(host='0.0.0.0', port=5000, debug=True,threaded=True)


