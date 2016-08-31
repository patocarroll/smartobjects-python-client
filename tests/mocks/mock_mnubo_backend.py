import uuid
from datetime import datetime

from .routes import route


class MockMnuboBackend(object):
    def __init__(self):
        self.clear()

    def clear(self):
        self.events = {}
        self.owners = {}
        self.objects = {}

    @route('POST', '^/oauth/.*')
    def auth(self, body, params):
        return 200, {
            "access_token": "<TOKEN>",
            "token_type": "Bearer",
            "expires_in": 3600,
            "scope": "ALL",
            "jti": str(uuid.uuid4())
        }

    # events
    def _process_event(self, event, must_exists):
        if "x_object" not in event or "x_device_id" not in event["x_object"]:
            return {"result": "error", "message": "Missing x_object.x_device_id"}

        if "x_event_type" not in event:
            return {"result": "error", "message": "Missing x_event_type"}

        device_id = event["x_object"]["x_device_id"]

        id = uuid.UUID(event['event_id']) if 'event_id' in event else uuid.uuid4()
        if id in self.events:
            return {"result": "error", "id": str(id), "message": "Event ID '{}' already exists".format(id)}

        if must_exists and device_id not in self.objects:
            return {"result": "error", "id": str(id), "message": "Object '{}' not found".format(device_id)}

        self.events[id] = event
        return {"result": "success", "id": str(id), "objectExists": device_id in self.objects}

    @route('POST', r'^/events(?:\?([a-z=_]+)?)?(?:&([a-z=_]+)?)?$')
    def post_events(self, body, params):
        must_exists, report_result = False, False
        for p in params:
            if p and p.startswith('must_exist'):
                must_exists = p.endswith('true')
            if p and p.startswith('report_result'):
                report_result = p.endswith('true')

        result = [self._process_event(event, must_exists) for event in body]
        failed = filter(lambda r: r['result'] != "success", result)

        if report_result:
            return 207 if failed else 200, result
        else:
            if failed:
                return 400, failed[0]['message']
            else:
                return 200, None

    @route('POST', '^/objects/(.+)/events(?:\?([a-z=_]+)?)?$')
    def post_events_on_object(self, body, params):
        [event.update({'x_object': {'x_device_id': params[0]}}) for event in body]
        result = [self._process_event(event, True) for event in body]
        failed = filter(lambda r: r['result'] != "success", result)

        return 207 if failed else 200, result

    @route('GET', '^/events/exists/(.+)$')
    def get_events_exists(self, params):
        return 200, {params[0]: uuid.UUID(params[0]) in self.events}

    @route('POST', '^/events/exists$')
    def post_events_exist(self, body, _):
        return 200, [{id: uuid.UUID(id) in self.events} for id in body]

    # objects
    def _process_object(self, obj, update=False):
        if 'x_device_id' not in obj:
            return {"result": "error", "message": "x_device_id cannot be null or empty."}

        dev_id = obj['x_device_id']

        # x_device_id is mandatory for object creation
        if dev_id not in self.objects and 'x_object_type' not in obj:
            return {"result": "error", "id": dev_id, "message": "x_object_type cannot be null or empty."}

        if dev_id in self.objects:
            if update:
                self.objects[dev_id].update(obj)
            else:
                return {"result": "error", "id": dev_id, "message": "Object with device id '{}' already exists.".format(dev_id)}
        else:
            obj['x_registration_date'] = datetime.now().isoformat()
            self.objects[dev_id] = obj

        return {"result": "success", "id": dev_id}

    @route('POST', '^/objects$')
    def post_one_object(self, body, _):
        result = self._process_object(body)
        if result['result'] != "success":
            return 400, result["message"]
        else:
            return 201, body

    @route('PUT', '^/objects$')
    def put_batch_objects(self, body, _):
        result = [self._process_object(obj, True) for obj in body]
        failed = filter(lambda r: r['result'] != "success", result)
        return 207 if failed else 200, result

    @route('PUT', '^/objects/(.+)$')
    def put_object_by_id(self, body, params):
        dev_id = params[0]
        if dev_id not in self.objects:
            return 400, "Object with x_device_id '{}' not found.".format(dev_id)
        self.objects[dev_id].update(body)
        return 200, None

    @route('DELETE', '^/objects/(.+)$')
    def delete_objects(self, _, params):
        dev_id = params[0]

        if dev_id not in self.objects:
            return 400, "Object with x_device_id '{}' not found.".format(dev_id)

        del self.objects[dev_id]
        return 200, None

    @route('GET', '^/objects/exists/(.+)$')
    def get_objects_exists(self, params):
        dev_id = params[0]
        return 200, {dev_id: dev_id in self.objects}

    @route('POST', '^/objects/exists$')
    def post_objects_exists(self, body, _):
        return 200, [{dev_id: dev_id in self.objects} for dev_id in body]

    # owners
    def _process_owner(self, owner, update=False):
        if 'username' not in owner:
            return {"result": "error", "message": "username cannot be null or empty."}

        username = owner['username']

        if 'invalid_property' in owner:
            return {"result": "error", "id": username, "message": "Unknown field 'invalid_property'"}

        if username in self.owners:
            if update:
                self.owners[username].update(owner)
            else:
                return {"result": "error", "id": username, "message": "The username '{}' is already in use.".format(username)}
        else:
            owner['x_registration_date'] = datetime.now().isoformat()
            self.owners[username] = owner

        return {"result": "success", "id": username}

    @route('POST', '^/owners/?$')
    def post_one_owner(self, body, _):
        result = self._process_owner(body)
        if result['result'] != 'success':
            return 400, result['message']
        else:
            return 201, self.owners[body['username']]

    @route('PUT', '^/owners$')
    def put_owners(self, body, _):
        result = [self._process_owner(owner, True) for owner in body]
        failed = filter(lambda r: 'result' in r and r['result'] == "error", result)
        return 207 if failed else 200, result

    @route('PUT', '^/owners/(.+)$')
    def put_owner_by_id(self, body, params):
        username = params[0]
        if username not in self.owners:
            return 400, "Owner '{}' not found.".format(username)

        self.owners[username].update(body)
        return 200, None

    @route('DELETE', '^/owners/(.+)$')
    def delete_owners(self, body, params):
        username = params[0]

        if body and 'x_timestamp' in body:
            # actual SmartObjects platform would tag the deletion with the provided timestamp
            pass

        if username not in self.owners:
            return 400, "Owner '{}' not found.".format(username)

        del self.owners[username]
        return 200, None

    @route('POST', '^/owners/(.+)/objects/(.+)/claim$')
    def post_owners_claim(self, _, params):
        username, device_id = params

        if username not in self.owners:
            return 400, "Owner '{}' not found.".format(username)

        if device_id not in self.objects:
            return 400, "Object with x_device_id '{}' not found.".format(device_id)

        self.objects[device_id]['x_owner'] = username
        return 200, None

    @route('POST', '^/owners/(.+)/password$')
    def put_owners_password(self, body, params):
        username = params[0]

        if username not in self.owners:
            return 400, "Owner '{}' not found.".format(username)

        if 'x_password' not in body:
            return 400, "x_password cannot be null or empty."

        self.owners[username]['x_password'] = body['x_password']
        return 200, None

    @route('GET', '^/owners/exists/(.+)')
    def get_owner_exists(self, params):
        username = params[0]
        return 200, {username: username in self.owners}

    @route('POST', '^/owners/exists/?$')
    def post_owners_exist(self, body, _):
        return 200, [{username: username in self.owners} for username in body]

    # search
    def _validate_query(self, query):
        # /!\ this validation is for test purpose only and do not implement all checks done by the actual API
        errors = []
        if not query:
            errors.append("Query cannot be empty or null.")
        else:
            if 'from' not in query:
                errors.append("a query must have a 'from' field")
            if 'limit' in query and not 1 <= query['limit'] <= 100000:
                errors.append("limit must be an integer between 1 and 100000")

        return errors

    @route('POST', '^/search/basic$')
    def post_search_basic(self, query, _):
        errors = self._validate_query(query)
        if errors:
            return 400, errors[0]

        result = {}
        if query['from'] == 'hardcoded:grouping-by-time-interval':
            result = {
                "columns": [{"label": "month", "type": "datetime"}, {"label": "COUNT(*)", "type": "long"}],
                "rows": [["2015-01-01T05:00:00.000Z", 400], ["2015-02-01T05:00:00.000Z", 178185], ["2015-03-01T05:00:00.000Z", 246871], ["2015-04-01T05:00:00.000Z", 7234234]]
            }

        return 200, result

    @route('POST', '^/search/validateQuery$')
    def post_search_validate(self, query, _):
        errors = self._validate_query(query)

        return 200, {
            'isValid': len(errors) == 0,
            'validationErrors': errors
        }

    @route('GET', '^/search/datasets$')
    def get_datasets(self, params):
        # hardcoded dataset from https://sop.mtl.mnubo.com/apps/doc/api.html#get-api-v3-search-datasets
        dataset = [
            {"key": "object", "displayName": "Objects", "fields": [{"key": "x_device_id", "highLevelType": "TEXT", "description": "Reserved field", "containerType": "none", "primaryKey": False}, {"key": "x_collections.id", "highLevelType": "TEXT", "displayName": "Collection id", "description": "Collection unique identifier", "containerType": "none", "primaryKey": False}]},
            {"key": "owner", "displayName": "Owners", "fields": [{"key": "username", "highLevelType": "TEXT", "displayName": "Username", "description": "Owner unique identifier", "containerType": "none", "primaryKey": True}, {"key": "x_registration_date", "highLevelType": "DATETIME", "description": "Reserved field", "containerType": "none", "primaryKey": False}]},
            {"key": "session", "displayName": "Sessions", "fields": [{"key": "x_start.x_timestamp", "highLevelType": "DATETIME", "displayName": "Event timestamp", "description": "The date and time the event happened", "containerType": "none", "primaryKey": False}, {"key": "x_start.x_received_timestamp", "highLevelType": "DATETIME", "displayName": "Event received timestamp", "description": "The date and time the event have been received by Mnubo", "containerType": "none", "primaryKey": False}]},
            {"key": "event", "displayName": "Events", "fields": [{"key": "x_object.x_device_id", "highLevelType": "TEXT", "description": "Reserved field", "containerType": "none", "primaryKey": False}, {"key": "event_id", "highLevelType": "TEXT", "displayName": "Event id", "description": "The unique UUID identifier of the event", "containerType": "none", "primaryKey": True}]}
        ]
        return 200, dataset

    # for tests on API manager itself
    @route('GET', '^/api_manager\??(.*)$')
    def get_api_manager(self, params):
        return 200, params

    @route('POST', '^/api_manager\??(.*)$')
    def post_api_manager(self, body, params):
        return 200, (params, body)

    @route('PUT', '^/api_manager\??(.*)$')
    def put_api_manager(self, body, params):
        return 200, (params, body)

    @route('DELETE', '^/api_manager\??(.*)$')
    def delete_api_manager(self, body, params):
        return 200, (params, body)
