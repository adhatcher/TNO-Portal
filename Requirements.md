# Requirements

Create a python flask application that does the following things:

## Non Functional Requirements

The application should abide by the following requirements throughout the application:

1. Adhere to security best practices and standards
2. Adhere to pylint standards and pythonic programming best practices
3. Include pytest, metrics and logging for all functions created
4. Create application to be run as a docker container
5. Application will run on an unraid server.
6. Any persistent data/config files and or logs should be stored in an external volume, not in the container
7. Utilize a MongoDB no-sql database for data storage/retention that can be configured in the docker container.
   1. for testing purposes the data is TNO-MongoDB on 192.160.50.4:27017
8. Provide real-time translation to English, French, Spanish, Russian or Portguese, based on users settings
9. Use Poetry for package management (including the use of a virtual env)
10. Crete a .gitignore file to exclude unnecessary files from git repo
11. Create a .dockerignore file to exclude unnecessary files from docker container
12. Include a Makefile with build, test, coverage and install and run commands configured.
13. Use gunicorn for the flask webserver engine.
14. Include a README.md file with instructions on how to build, install and run the app and requirements.

## Functional Requirements

The web application should do the following:

## Stage 1

### Welcome Screen

Welcome screen that is the landing page for the application.

1. Route for the welcome screen should be "/"
2. Should have the option to log in or create a new account.
3. Contain a "Language Settings" dropdown in the upper right corner to determine the lanugage to display the pages in.  
   1. this setting should be used througout the entire application
   2. This setting shoudl be stored as a cookie and the app should check to see if this exists and use that setting automatically.
   3. If the user is a returning user, their login name should be displayed on the welcome page. (also stored as a cookie)
4. Welcome screen should display "Welcome to the Home for TNO, TON and TCF for Puzzles and Survival".  If the user is a returning user, display:
"Welcome ${USER} to the home of TNO, TCF and TON for Puzzles and Survival".
   1. Background for the page should have some type of Puzzles and Survival based artwork, with transparency set to 40%.
      1. Make sure the text is clearly visibl on the page and is not washed out by the background.
5. When the Create New Account option is selected, users should be prompted to enter a code of "TNO".
   1. If the code is entered correctly, take the user to a page where they can create an accont.  

### Create New Account

1. The create new account page should contain the following fields and the data should e stored in a no-sql database that will reside in the /app/data directory.
1. The /app/data directory should be created as a volume in docker.

Display the following fields:

1. Username (On Line 1)
   1. After the username has been entered, (field is not blank, focus moves away from field to Password field), verify the username is available and not already taken
1. Password
   1. Encrypted and masked
   2. Contains a "show unmasked icon to show plain text
   3. Located on under username
   4. Password should meet a min standard of 8 characters, 1 capital letter, 1 numberic character and 1 non-alpha character
1. Confirm Password
   1. Encrypted and masked
   2. Contains a "show unmasked icon to show plain text
   3. Located on under username
1. Verify Password Display field showing if passwords match:
   1. Shows true when:
      1. Password and Confirm Password fields match
      2. Password meet standards of 8 characters, 1 capital letter, 1 numberic character and 1 non-alpha character
      3. Password is not blank
   2. Otherwise, show false.  
   3. If password and confirm password fields are blank, do not display anything.
1. When Confirm Passwords Match is true:
   1. Enable the "Create Account" button, located under the veriy password field

## Stage 2

When a user logs in, check to see if the user has data for at least 1 of the following fields:

1. First Name
2. Last Name
3. Email Address
4. Perferred Language

If none of these fields has a value, direct the user to a "User Info" page. If they do have at least one of these fields completed, direct them to the Accounts Page.

### User Info Page

This page should contain the following fields:

1. User Name (from login)
2. First Name (Required)
3. Last Name (Optional) and
4. Email address (Optional), used for password resets
5. Preferred Language (Same options that are available in the language selector at the top right of the screen)

Incude the following Buttons below the fields:

1. Save Info button
1. Reset Password
   1. Only enable if the user has entered a valid password that has been verified
1. Delete User
   1. only enable this if the user doesn't have any accounts created

### Accounts Page

Allows the user to enter the following information about their accounts.  Each row should have the following fields.

1. Title at the top of the page:
   1. Player Accounts for (username):

List the accounts for the user in a tablular form with the following fields:

1. Row selector (checkbox)
1. Account Name:
   1. Text Field
1. Account Type:
   1. Dropdown with the following choices: Main, Secondary, Farm
      1. These choices should be configurable in an admin screen and saved in the database
   2. User should only be allowed to have 1 account set to Main
1. Alliance:
   1. Dropdown with these choices: TNO, TCF, TNO, R&S
      1. These choices should be configurable in an admin screen and saved in the database

Below the rows, there should be the following buttons:

1. Delete Button which
   1. Deletes all rows that are checked (checkbox)
2. Add a new row
   1. Adds a new row and saves the existing rows

- Each user will have multiple accounts.
- When opening the accounts page, if there are no rows for the user, default the Account Name to the Users Name, the Account Type to Main and Alliance to TNO for the 1st row.
- Allow this row to be changed or saved.

### Admin Page

Create an admin page only available to users designated as Admin:

- Link to a page to allow CRUD actions to be performed on the Account Type option used in the Accounts Page
- Link to a page that allows CRUD actions to be performed on the Alliances used in the Accounts Page.

#### Account Type Maintenance Page

- Allow CRUD actions to be performed on the Account Types used on the Account Page

#### Alliance Maintenance Page

- Allow CRUD actions to be performed on the Account Types used on the Account Page

## Admin Accounts

- Set the user type for Eviseration to Admin by default.
- All other users should be created as normal users
- Create an User Admin page that provides the following:

1. Table of all users with the following information:
   1. check box
   2. Username
   3. First Name
   4. Last Name
   5. Email Address
   6. User type (drop down with User or Admin)
2. Button to Delete user(s)
   1. Delete should delete all the users accounts and the user

## Alliance user Page

Create a page that lists all of the users in alphabetical order (based on their username). Under each user, list all of the accounts, sorted by Main 1st, Secondary 2nd, then farm. 
For each account, show account name, account type and Alliance.

Add search capabilities to the top of the page and include the following:
Filter for account type:  All, Main, Secondary, Farm
Filter for Alliance: All, TNO, TCF, TON
Search box that will either search for an account or username

- Search box should return user and all accounts if the username or any of the accounts matches the search
- Filters should then be applied.

For example, if a serch for Vis kid is entered, with no filters, the following should be returned:

Eviseration:  Aaron Hatcher  adhatcher73@gmail.com

|Main|Secondary|Farm1|Farm2|Farm3|
|---|---|---|---|---|
|Eviseration (R&S)|The Vis (TNO)|Vis kid (R&S)|Baby Vis Doot Doot (R&S)|Baby_Shark (TCF)|
