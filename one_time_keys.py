from wsgiref.simple_server import make_server
from pyramid.config import Configurator
from pyramid.view import view_config
from pyramid.response import Response
from pymongo import MongoClient
from pymongo.collection import ReturnDocument
from bson.objectid import ObjectId
from bson.errors import InvalidId
import json
from random import randrange


class OneTimeKey:
    def __init__(self):
        self.keys = MongoClient('localhost', 27017).otk.keys

    def get_key(self):
        requested_key = self.keys.find_one_and_update(
            {'status': 0},
            {'$set': {'status': 1}}
        )
        if requested_key:
            key_id = str(requested_key['_id'])
            key_data = requested_key['key']
            return {
                'id': key_id,
                'key': key_data
            }

    def cancel_key(self, key_id):
        requested_key = self.keys.find_one_and_update(
            {'_id': ObjectId(key_id), 'status': 1},
            {'$set': {'status': 2}},
            return_document=ReturnDocument.AFTER
        )
        if requested_key:
            key_status = requested_key['status']
            return {
                'id': key_id,
                'status': key_status
            }

    def get_key_status(self, key_id):
        try:
            result = self.keys.find_one({'_id': ObjectId(key_id)})
        except InvalidId:
            return None
        else:
            if result:
                return {
                    'id': key_id,
                    'status': result['status']
                }

    def keys_count(self):
        left_keys_count = self.keys.find({'status': 0}).count()
        return {
            'count': left_keys_count
        }

    def generate_keys(self, quantity=1000):
        lower_chars = 'abcdefghijklmnopqrstuvwxyz'
        upper_chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
        digits = '0123456789'
        chars = lower_chars + upper_chars + digits
        len_chars = len(chars)
        db_keys = self.keys.find(
            {},
            {
                '_id': False,
                'key': True
            }
        )
        db_keys = [x['key'] for x in db_keys]
        key_list = []

        def generate_key():
            key = ''
            for __ in range(4):
                key += chars[randrange(len_chars)]
            return key

        for _ in range(quantity):
            while True:
                key = generate_key()
                if key not in db_keys:
                    break
            key_list.append(
                {
                    'key': key,
                    'status': 0
                }
            )
        if key_list:
            self.keys.insert_many(key_list)
            return True


otk = OneTimeKey()


@view_config(route_name='main', request_method='GET', renderer='json')
def info_view(request):
    return otk.keys_count()


@view_config(route_name='main', request_method='POST', renderer='json')
def generate_view(request):
    # if request.json_body:
    #     quantity = request.json_body['quantity']
    #     result = otk.generate_keys(quantity)
    # else:
    #     result = otk.generate_keys()
    try:
        quantity = request.json_body['quantity']
    except (KeyError, json.decoder.JSONDecodeError):
        result = otk.generate_keys()
    else:
        result = otk.generate_keys(quantity)
    if result:
        return Response(
            status='202 Accepted',
            content_type='application/json'
        )
    else:
        return Response(
            status='400 Bad Request',
            content_type='application/json'
        )


@view_config(route_name='main', request_method='PUT', renderer='json')
def get_view(request):
    return otk.get_key() or Response(
        body=json.dumps({'message': 'No keys available'}),
        status='400 Bad Request',
        content_type='application/json',
        charset='utf-8'
    )


@view_config(route_name='key', request_method='PUT', renderer='json')
def cancel_key_view(request):
    id = request.matchdict['key']
    try:
        status = otk.get_key_status(id)['status']
    except KeyError:
        return Response(
            status='404 Not Found',
            content_type='application/json'
        )
    else:
        if status == 0:
            return Response(
                body=json.dumps({'message': 'Key is not yet given'}),
                status='400 Bad Request',
                content_type='application/json',
                charset='utf-8'
            )
        elif status == 1:
            if otk.cancel_key(id):
                return Response(
                    status='202 Accepted',
                    content_type='application/json'
                )
            else:
                return Response(
                    status='500 Internal Server Error',
                    content_type='application/json'
                )
        else:
            return Response(
                body=json.dumps({'message': 'Key is already cancelled'}),
                status='400 Bad Request',
                content_type='application/json',
                charset='utf-8'
            )


@view_config(route_name='key', request_method='GET', renderer='json')
def get_status_view(request):
    id = request.matchdict['key']
    result = otk.get_key_status(id)
    return result or Response(
        status='404 Not Found',
        content_type='application/json'
    )


if __name__ == '__main__':
    with Configurator() as config:
        config.add_route('main', '/api/v1')
        config.add_route('key', '/api/v1/{key}')
        config.scan()
        app = config.make_wsgi_app()
    server = make_server('0.0.0.0', 6543, app)
    server.serve_forever()

