from psycopg2 import connect
import os
import logging 
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
        'port': env.get('OG_PORT', 7654)
    }
    conn = connect(**params)
    return conn

def create_table(conn):
    """check and create table by example

    Args:
        table_name (str): the name of the table
        corsor (type): the corsor type to get into operation with db
    """
    with conn:
        with conn.cursor() as cursor:
            cursor.execute("""
        
            SELECT *
            FROM book_eg.teachers
        ;""")
            rows = cursor.fetchall()
            for row in rows:
                  print("ID = ", row[0])
                  print("NAME= ",row[1])

    cnn.close()

cnn=create_conn()
create_table(cnn)
