#!/bin/bash

exec uwsgi --http-socket :8080 --master --module wsgi --thunder-lock --processes 8
