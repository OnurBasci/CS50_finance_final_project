import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
import time

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    #get rows of the current user
    rows = db.execute("select * from stocks where person_id = :idn", idn = session["user_id"])
    cash = db.execute("select cash from users where id = :idn", idn = session["user_id"])

    #update prices
    sum = 0;
    if len(rows)>0:
        for i in range(len(rows)):
            #update the users values
            info = lookup(rows[i]["symbol"])
            price = float(info["price"])
            share = rows[i]["shares"]
            total = share * price
            s_id = rows[i]["id"]
            sum += total
            db.execute("update stocks set price = :p, total = :t where id = :idn",
                        p=price, t=total, idn=s_id)
    #calculate the total
    sum += cash[0]["cash"]
    #get rows after update
    #rows = db.execute("select * from stocks where person_id = :idn",idn = session["user_id"])
    return render_template("index.html", rows=rows, cash = usd(cash[0]["cash"]), total=usd(sum))



@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    #get history row of the current user
    rows = db.execute("select * from history where person_id = :idn", idn = session["user_id"])
    return render_template("history.html", rows=rows)


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":
        #check if the symbol is provided
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)
        #check if the symbol is valid
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("the provided symbol is not valid", 403)
        #check if the share provided
        shares = request.form.get("share")
        if not shares:
            return apology("must provide share number", 403)
        #if it is not positive render apology
        shares = int(shares)
        if shares < 0:
            return apology("share must be positive", 403)

        #get the informations
        price = float(quote["price"])
        symbol = quote["symbol"]

        #get the users stock row containing the current infos of quote asked
        rows = db.execute("select shares from stocks where symbol =:s and person_id = :pd", s = symbol, pd = session["user_id"])
        #check if the name is valid
        if len(rows)>0:
            current_shares = rows[0]["shares"]

            #check if the user have enough stock to sell
            if shares > current_shares:
                return apology("Not enough share to sell", 403)

            #add the sell to the history table
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')
            db.execute("INSERT INTO history (symbol, shares, transact_date, price, person_id) VALUES (:sy, :sh, :td, :p, :pe)",
                                sy=symbol, sh=-shares, td=current_time, p=price, pe=session["user_id"])

            #modify the stock table
            new_shares = current_shares - shares
            new_total = new_shares * price

            db.execute("update stocks set shares = :sh , total = :t where person_id = :ind and symbol = :sy",
                        sh=new_shares, t=new_total, ind=session["user_id"], sy = symbol)

            #increase the cash
            user_row = db.execute("select cash from users where id = :idn", idn=session["user_id"])
            cash = user_row[0]["cash"]
            to_add = shares * price
            db.execute("update users set cash = :ch where id = :idn", ch=(cash+to_add), idn=session["user_id"])

            return redirect("/")

        else:
            return apology("you don't own any stock from this company", 403)
    return render_template("sell.html")



@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        #check if the symbol is provided
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)
        #check if the symbol is valid
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("the provided symbol is not valid", 403)
        #check if the share is entered
        shares = request.form.get("share")
        if not shares:
            return apology("must provide share number", 403)
        #if it is not positive render apology
        shares = int(shares)
        if shares < 0:
            return apology("share must be positive")
        #get the informations
        price = float(quote["price"])
        name = quote["name"]
        symbol = quote["symbol"]
        total = price * shares
        #check if the user has enough money to buy
        #get the users cash
        row = db.execute("select cash from users where id = :id", id = session["user_id"]);
        cash = row[0]["cash"]
        if cash > total:
            #check if the user owns already choosed compagny's stock
            owns = False
            row_index = 0
            rows = db.execute("select * from stocks where person_id = :idn",idn = session["user_id"]);
            print(rows)
            for x in range(len(rows)):
                if name in rows[x].values():
                    print(rows[x])
                    row_index = x
                    owns = True
                    break
            if owns:
                #update the prices
                total1 = rows[x]["shares"] * price
                total1 +=total
                #change values
                db.execute("update stocks set shares = :sh , price = :p, total = :t where id = :ind",
                            sh=(rows[row_index]["shares"]+shares), p=price, t=total1,ind=rows[row_index]["id"])
            else:
                #add in database if the row does not exist
                db.execute("INSERT INTO stocks (symbol, name, shares, price, total, person_id) VALUES (:sy, :n, :sh, :pr, :t, :pe)",
                            sy=symbol, n=name, sh=shares, pr=price, t=total, pe=session["user_id"])

            #update the history table
            #get time
            current_time = time.strftime('%Y-%m-%d %H:%M:%S')

            db.execute("INSERT INTO history (symbol, shares, transact_date, price, person_id) VALUES (:sy, :sh, :td, :p, :pe)",
                                sy=symbol, sh=shares, td=current_time, p=price, pe=session["user_id"])

            #modify the cash
            cash -= total
            #update the database
            db.execute("update users set cash = :cash where id = :id", cash=cash, id = session["user_id"])
            return redirect("/")
        else:
            return apology("Not enough money")
    else:
        return render_template("buy.html")





@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():

    if request.method == "POST":
        #check if the symbol is provided
        if not request.form.get("symbol"):
            return apology("must provide a symbol", 403)
        #check if the symbol is valid
        quote = lookup(request.form.get("symbol"))
        if quote == None:
            return apology("the provided symbol is not valid", 403)
        #show the page with the compagny information
        name = quote["name"]
        price = quote["price"]
        symbol = quote["symbol"]
        return render_template("quoted.html", name=name, price=usd(price), symbol=symbol)
    else:
        return render_template("quote.html")


#@app.route("/quoted")
#@login_required
#def quoted():
#    return reder_template("quoted.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    #if the methode is post
    if request.method == "POST":
        #if user does not provide a username
        if not request.form.get("username"):
            return apology("must provide username", 403)

        #if user does not provide a password or password verifier
        if not request.form.get("password"):
            return apology("must provide password", 403)
        #check password match
        password = request.form.get("password")
        p_verification = request.form.get("password_verification")
        if password != p_verification:
            return apology("Passwords do not check", 403)
        #if all works as expected add the user to the database
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :hashed_pw)", username = request.form.get("username"), hashed_pw = generate_password_hash(password))
        #when the user is aded to the database opens the login page
        return redirect("/login")
    else:
        return render_template("register.html",)






def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
