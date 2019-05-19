# Talking Scores

## Prerequisites

1. A working Python 3 installation

## Installation

1. Create a virtual environment for the python requirements
   ``` 
   python -m venv .talkingscore-env
   ```
1. Install the required python modules
   ``` 
   pip install -r requirements
   ```

## Running a server

1. Ensure the virtual environment is active (you should see `(.talkingscores-env)` in your prompt).
    ```
    source .talkingscores-env/bin/activate
    ```
1. Run the local Django server.
    ```
    python ./manage.py runserver
    ```


