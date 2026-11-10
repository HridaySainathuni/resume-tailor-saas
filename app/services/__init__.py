"""Service layer: pure logic with no Flask request handling.

Routes in app/api stay thin. They validate input, call a service, and
return a response. Services can be tested without a request context.
"""
