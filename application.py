import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash
from passlib.apps import custom_app_context as pwd_context
import datetime

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
    stocks = db.execute("SELECT stock, SUM(shares) as total_shares FROM portfolio WHERE user_id=:userid GROUP BY stock HAVING total_shares > 0", userid=session["user_id"])
    user_cash = db.execute("SELECT cash FROM users WHERE id=:userid", userid=session["user_id"])

    portfolio_value = 0

    for stock in stocks:
        quote = lookup(stock["stock"])
        price = quote["price"]
        stock["price"] = price
        name = quote["name"]
        stock["name"] = name
        shares = stock["total_shares"]
        value = price * stock["total_shares"]
        stock["value"] = value
        portfolio_value = portfolio_value + value

    # Get current's user's cash
    current_cash = user_cash[0]["cash"]
    total_cash_portfolio = portfolio_value + current_cash

    return render_template("index.html", stocks=stocks, current_cash=current_cash, total_cash_portfolio=total_cash_portfolio)



@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """ Change user's password"""
    if request.method == "POST":

        old_password = request.form.get("password")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        rows = db.execute("SELECT * FROM users WHERE id=:userid", userid=session["user_id"])

        # Ensure password was submitted
        if not old_password:
            return apology("must provide password", 400)
        elif not new_password:
            return apology("must provide new password",400)
        elif not confirmation:
            return apology("must confirm password", 400)

        # Check if passwords match
        if new_password != confirmation:
            return apology("Passwords must match!", 400)

        # Check if old password is correct and update new password
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], old_password):
            return apology("invalid password", 400)

        # Generate new hash for user
        new_hash = generate_password_hash(new_password)

        # Update new password
        update_password = db.execute("UPDATE users SET hash=:hash WHERE id=:userid",
        hash=new_hash,userid=session["user_id"])

        return redirect ("/")

    else:
        return render_template("change_password.html")


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        quote = request.form.get("symbol").upper()

        if not quote:
            return apology("Please enter the name of the stock",400)
        try:
            stock = lookup(quote)
            price = stock["price"]
        except:
            return apology("Symbol does not exist", 400)

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Please enter number of shares", 400)
        if shares < 0:
            return apology("Please enter a positive number of shares", 400)

        current_user = db.execute("SELECT cash from users WHERE id = :userid", userid = session["user_id"])
        current_cash = current_user[0]["cash"]

        if shares*price > current_cash:
            return apology("You do not have enough cash to make this purchase", 400)

        # Update current user's cash balance if they bought the stock
        updated_cash = current_cash - shares*price
        db.execute("UPDATE users SET cash=:updated_cash WHERE id=:userid", userid = session["user_id"], updated_cash=updated_cash)

        # Insert purchase into database
        db.execute("INSERT INTO portfolio(user_id, stock, shares, price, time, action) VALUES(:userid, :stock, :shares, :price, :time, :action)",\
        userid=session["user_id"], stock=quote, shares=shares, price=price, time=datetime.datetime.now(), action="BOUGHT")
        
        flash("Bought!")

        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    history = db.execute("SELECT * FROM portfolio WHERE user_id=:userid", userid=session["user_id"])

    for row in history:
        stock = row["stock"]
        price = row["price"]
        time = row["time"]
        action = row["action"]

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

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
    """Get stock quote."""
    if request.method == "POST":
        try:
            quote = lookup(request.form.get("symbol"))
            return render_template("quoted.html", name=quote['name'], symbol=quote['symbol'], price=quote['price'])
        except:
            return apology("Invalid Ticker Symbol", 400)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():

    """Register user"""

    session.clear()

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        hash = generate_password_hash(request.form.get("password"))

        if not username:
            return apology("Please enter a username",400)
        elif not password:
            return apology("Please enter a password",400)
        elif password != confirmation:
            return apology("Passwords do not match!", 400)

        # Query database for username
        check_existing_user = db.execute("SELECT * from users WHERE username=:username", username=username)

        # Check if username is already in the database
        if len(check_existing_user) == 1:
            return apology("Username already exists", 400)

        elif len(check_existing_user) != 1:
            new_user = db.execute("INSERT into users (username, hash) VALUES (:username, :hash)", username=username, hash=hash)

            user_row = db.execute("SELECT id from users WHERE username=:username", username=username)

            # Remember current user in the session
            session["user_id"] = user_row[0]["id"]

        return redirect("/")

    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "POST":

        quote = request.form.get("symbol").upper()

        if not quote:
            return apology("Please enter the name of the stock",400)

        try:
            stock = lookup(quote)
            price = stock["price"]
        except:
            return apology("Symbol does not exist", 400)

        try:
            shares = int(request.form.get("shares"))
        except:
            return apology("Please enter number of shares", 400)
        if shares < 0:
            return apology("Please enter a positive number of shares", 400)

        # Check current user's portfolio
        current_portfolio = db.execute("SELECT stock, SUM(shares) as total_shares FROM portfolio WHERE user_id=:userid AND stock=:stock \
        GROUP BY stock", userid=session["user_id"], stock=quote)

        user_cash = db.execute("SELECT cash FROM users WHERE id=:userid", userid=session["user_id"])
        current_cash = user_cash[0]["cash"]

        # Check if user already has stock in portfolio, or sufficient shares to sell
        if len(current_portfolio) != 1:
            return apology("Stock does not exist in your portfolio")

        elif len(current_portfolio) == 1:

            current_shares = int(current_portfolio[0]["total_shares"])

            if shares > current_shares:
                return apology("You do not have enough shares to sell")
            else:
                updated_cash = current_cash + (shares*price)

                # Update user's cash balance and insert transaction into transaction history
                db.execute("UPDATE users SET cash=:updated_cash WHERE id=:userid", userid = session["user_id"], updated_cash=updated_cash)

                db.execute("INSERT INTO portfolio(user_id, stock, shares, price, time, action) VALUES(:userid, :stock, :shares, :price, :time, :action)",\
                userid=session["user_id"], stock=quote, shares=(-1)*shares, price=price, time=datetime.datetime.now(), action="SOLD")
                
                flash("Sold!")

        return redirect("/")

    else:
        db.execute("SELECT stock, SUM(shares) as total_shares FROM portfolio WHERE user_id=:userid GROUP BY stock HAVING total_shares > 0",userid=session["user_id"])
        return render_template("sell.html")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
