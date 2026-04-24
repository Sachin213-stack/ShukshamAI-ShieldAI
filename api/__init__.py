# api/__init__.py
# What it contains: Usually nothing (it can be empty), or code to initialize the package.
# Why it is important: This file tells Python that the `api` folder is a "package" (a collection of modules). 
#                     Without it, Python wouldn't know it's allowed to import files from this directory.
# Connectivity: This file allows `main.py` to do things like `from api.routes import router`. 
#               It connects the files inside this folder to the outside world.
