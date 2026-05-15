
from flask import Flask, request, redirect, session, g, render_template_string
import sqlite3, os, json, datetime, traceback
from functools import wraps

APP_VERSION="SD Invoice Python Full V2.2 Working"
DB=os.path.join(os.path.dirname(os.path.abspath(__file__)),"sd_invoice_v22.db")
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","sd-invoice-v22-secret")

def conn():
    if "db" not in g:
        g.db=sqlite3.connect(DB)
        g.db.row_factory=sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(error):
    d=g.pop("db",None)
    if d: d.close()

def init_db():
    c=sqlite3.connect(DB)
    x=c.cursor()
    x.execute("CREATE TABLE IF NOT EXISTS clients(id INTEGER PRIMARY KEY AUTOINCREMENT,company_name TEXT,email TEXT,user_id TEXT,password TEXT,gstin TEXT,pan TEXT,state TEXT,state_code TEXT,phone TEXT,address TEXT,payment_terms TEXT,plan_code TEXT DEFAULT 'premium',subscription_start TEXT,subscription_end TEXT,footer_text TEXT DEFAULT 'This invoice generated from SD Invoice portal.',status TEXT DEFAULT 'Active')")
    x.execute("CREATE TABLE IF NOT EXISTS branches(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,branch_code TEXT,name TEXT,prefix TEXT)")
    x.execute("CREATE TABLE IF NOT EXISTS customers(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,name TEXT,gstin TEXT,pan TEXT,phone TEXT,email TEXT,state TEXT,state_code TEXT,address TEXT,shipping_name TEXT,shipping_address TEXT,shipping_state TEXT,shipping_state_code TEXT,due_days INTEGER DEFAULT 15)")
    x.execute("CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,name TEXT,hsn TEXT,price REAL DEFAULT 0,gst REAL DEFAULT 0,unit TEXT DEFAULT 'Nos')")
    x.execute("CREATE TABLE IF NOT EXISTS rate_contracts(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,customer_id INTEGER,product_id INTEGER,customer_name TEXT,item_name TEXT,hsn TEXT,uom TEXT,approved_rate REAL DEFAULT 0,gst REAL DEFAULT 0,valid_from TEXT,valid_to TEXT,status TEXT DEFAULT 'Active',remarks TEXT)")
    x.execute("CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,branch_id INTEGER,invoice_type TEXT,invoice_no TEXT,invoice_date TEXT,due_date TEXT,customer_id INTEGER,customer_name TEXT,taxable REAL DEFAULT 0,gst_amount REAL DEFAULT 0,total REAL DEFAULT 0,status TEXT DEFAULT 'Unpaid',invoice_json TEXT)")
    x.execute("CREATE TABLE IF NOT EXISTS receipts(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,invoice_id INTEGER,receipt_no TEXT,receipt_date TEXT,amount REAL DEFAULT 0,payment_mode TEXT,payment_ref TEXT,remarks TEXT)")
    x.execute("CREATE TABLE IF NOT EXISTS credit_notes(id INTEGER PRIMARY KEY AUTOINCREMENT,client_id INTEGER,invoice_id INTEGER,credit_note_no TEXT,credit_note_date TEXT,customer_name TEXT,amount REAL DEFAULT 0,reason TEXT)")
    x.execute("SELECT COUNT(*) FROM clients")
    if x.fetchone()[0]==0:
        start=datetime.date.today().isoformat()
        end=(datetime.date.today()+datetime.timedelta(days=365)).isoformat()
        x.execute("INSERT INTO clients(company_name,email,user_id,password,gstin,pan,state,state_code,phone,address,payment_terms,subscription_start,subscription_end) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",("Demo Client Company","demo@sdinvoice.com","admin","1234","24ABCDE1234F1Z5","ABCDE1234F","Gujarat","24","9999999999","Ahmedabad, Gujarat","As per agreement",start,end))
        cid=x.lastrowid
        x.execute("INSERT INTO branches(client_id,branch_code,name,prefix) VALUES(?,?,?,?)",(cid,"BR-001","Main Branch","INV"))
    c.commit(); c.close()
init_db()

def req(f):
    @wraps(f)
    def w(*a,**k):
        if not session.get("login_type"): return redirect("/")
        return f(*a,**k)
    return w

def cid():
    if session.get("login_type")=="superadmin":
        s=session.get("active_client_id")
        if s: return s
        r=conn().execute("SELECT id FROM clients ORDER BY id LIMIT 1").fetchone()
        return r["id"] if r else None
    return session.get("client_id")

def fl(v,d=0):
    try: return float(v if v not in ("",None) else d)
    except: return float(d)
def today(): return datetime.date.today().isoformat()
def sc(g): return (g or "")[:2] if (g or "")[:2].isdigit() else ""
def nextno(t,p,cidv):
    n=conn().execute(f"SELECT COUNT(*) c FROM {t} WHERE client_id=?",(cidv,)).fetchone()["c"]+1
    return f"{p}-{datetime.date.today().year}-{str(n).zfill(5)}"

CSS="""<style>
body{font-family:Arial;margin:0;background:#eef4fb;color:#00112b}header{background:#123b63;color:white;padding:18px 24px;display:flex;justify-content:space-between}header a{color:white}.tabs{padding:12px;background:#e7f0fb}.tabs a{background:#dbeafe;color:#00112b;padding:10px 13px;border-radius:8px;text-decoration:none;margin:4px;display:inline-block;font-weight:bold}section{background:white;margin:16px;padding:20px;border-radius:14px;border:1px solid #cbd5e1}.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}input,select{padding:10px;border:1px solid #cbd5e1;border-radius:8px;width:100%;box-sizing:border-box}button,.btn{background:#16813a;color:white;border:0;border-radius:8px;padding:10px 14px;font-weight:bold;text-decoration:none;display:inline-block}.btn{background:#0f3157}.danger{background:#b91c1c}table{width:100%;border-collapse:collapse;margin-top:14px}th,td{border:1px solid #cbd5e1;padding:9px}th{background:#e8f0fb}.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}.kpi{background:white;border:1px solid #cbd5e1;border-radius:12px;padding:14px}.kpi b{font-size:24px}.err{color:#b91c1c;font-weight:bold}.note{font-size:12px;color:#64748b;text-align:center;border-top:1px solid #ddd;padding-top:10px;margin-top:20px}@media(max-width:900px){.grid,.kpis{grid-template-columns:1fr}}@media print{header,.tabs,.toolbar{display:none}section{border:0;margin:0}.btn,button{display:none}}</style>"""
TOP="""<!DOCTYPE html><html><head><title>{{version}}</title>"""+CSS+"""</head><body><header><h2>{{version}}</h2><div>{{session.get('user')}} | <a href="/logout">Logout</a></div></header><div class="tabs"><a href="/dashboard">Dashboard</a>{% if session.get('login_type')=='superadmin' %}<a href="/clients">Clients</a>{% endif %}<a href="/company">Company/Profile</a><a href="/branches">Branches</a><a href="/masters">Masters</a><a href="/roc">Rate Contract</a><a href="/invoices">Invoice</a><a href="/receipts">Receipts</a><a href="/ledger">Ledger</a><a href="/credit-notes">Credit Note</a><a href="/gst-gsp">GST/GSP</a><a href="/tally-sap">Tally/SAP</a></div>"""
END="</body></html>"
def page(body,**kw): return render_template_string(TOP+body+END,version=APP_VERSION,**kw)

@app.errorhandler(Exception)
def err(e):
    return render_template_string("<html><head>"+CSS+"</head><body><section><h1>Application Error</h1><p class='err'>{{e}}</p><pre>{{tr}}</pre><a class='btn' href='/'>Login</a></section></body></html>",e=str(e),tr=traceback.format_exc()),500

@app.route("/")
def login():
    return render_template_string("""<!DOCTYPE html><html><head><title>{{version}}</title>"""+CSS+"""</head><body style="background:#123b63;min-height:100vh;display:flex;align-items:center;justify-content:center"><section style="width:720px"><h1>{{version}}</h1><p><b>Super Admin:</b> superadmin / admin123</p><p><b>Demo Client:</b> demo@sdinvoice.com / admin / 1234</p>{% if error %}<p class="err">{{error}}</p>{% endif %}<form method="post" action="/login" class="grid" style="grid-template-columns:1fr"><select name="login_type"><option value="superadmin">Super Admin</option><option value="client">Client</option></select><input name="email" placeholder="Client Email"><input name="user_id" placeholder="User ID" value="superadmin"><input name="password" type="password" placeholder="Password" value="admin123"><button>Login</button></form></section></body></html>""",version=APP_VERSION)

@app.post("/login")
def do_login():
    lt=request.form.get("login_type"); email=request.form.get("email","").strip(); uid=request.form.get("user_id","").strip(); pwd=request.form.get("password","").strip()
    if lt=="superadmin" and uid=="superadmin" and pwd=="admin123":
        session.clear(); session["login_type"]="superadmin"; session["user"]="superadmin"; return redirect("/dashboard")
    r=conn().execute("SELECT * FROM clients WHERE email=? AND user_id=? AND password=? AND status='Active'",(email,uid,pwd)).fetchone()
    if r:
        session.clear(); session["login_type"]="client"; session["client_id"]=r["id"]; session["user"]=uid; return redirect("/dashboard")
    return render_template_string("""<!DOCTYPE html><html><head>"""+CSS+"""</head><body><section><p class='err'>Invalid login</p><a href="/">Back</a></section></body></html>""")

@app.route("/logout")
def logout(): session.clear(); return redirect("/")

@app.route("/dashboard")
@req
def dashboard():
    c=cid(); client=conn().execute("SELECT * FROM clients WHERE id=?",(c,)).fetchone()
    counts={k:conn().execute(f"SELECT COUNT(*) c FROM {t} WHERE client_id=?",(c,)).fetchone()["c"] for k,t in [("branches","branches"),("customers","customers"),("products","products"),("invoices","invoices")]}
    counts["clients"]=conn().execute("SELECT COUNT(*) c FROM clients").fetchone()["c"]
    return page("""<section><h2>Dashboard</h2><div class="kpis"><div class="kpi">Clients<br><b>{{counts.clients}}</b></div><div class="kpi">Branches<br><b>{{counts.branches}}</b></div><div class="kpi">Customers<br><b>{{counts.customers}}</b></div><div class="kpi">Products<br><b>{{counts.products}}</b></div><div class="kpi">Invoices<br><b>{{counts.invoices}}</b></div></div><h3>Active Client</h3><p>{{client.company_name}} | {{client.email}} | {{client.subscription_start}} to {{client.subscription_end}}</p></section>""",counts=counts,client=client)

@app.route("/clients")
@req
def clients():
    rows=conn().execute("SELECT * FROM clients ORDER BY id DESC").fetchall()
    return page("""<section><h2>Client Registration</h2><form method="post" action="/client/save" class="grid"><input name="company_name" placeholder="Company Name" required><input name="email" placeholder="Email" required><input name="user_id" value="admin"><input name="password" value="1234"><input name="gstin" placeholder="GSTIN"><input name="pan" placeholder="PAN"><input name="phone" placeholder="Phone"><input name="state" placeholder="State"><input name="state_code" placeholder="State Code"><input name="address" placeholder="Address"><select name="status"><option>Active</option><option>Inactive</option><option>Suspended</option></select><button>Save Client</button></form></section><section><h2>Clients</h2><table><tr><th>Company</th><th>Email</th><th>Status</th><th>Action</th></tr>{% for r in rows %}<tr><td>{{r.company_name}}</td><td>{{r.email}}</td><td>{{r.status}}</td><td><a class="btn" href="/select-client/{{r.id}}">Work as Client</a></td></tr>{% endfor %}</table></section>""",rows=rows)

@app.post("/client/save")
@req
def client_save():
    f=request.form; start=today(); end=(datetime.date.today()+datetime.timedelta(days=365)).isoformat()
    conn().execute("INSERT INTO clients(company_name,email,user_id,password,gstin,pan,state,state_code,phone,address,subscription_start,subscription_end,status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(f.get("company_name"),f.get("email"),f.get("user_id"),f.get("password"),f.get("gstin"),f.get("pan"),f.get("state"),f.get("state_code") or sc(f.get("gstin")),f.get("phone"),f.get("address"),start,end,f.get("status")))
    new=conn().execute("SELECT last_insert_rowid() id").fetchone()["id"]; conn().execute("INSERT INTO branches(client_id,branch_code,name,prefix) VALUES(?,?,?,?)",(new,"BR-001","Main Branch","INV")); conn().commit(); return redirect("/clients")
@app.route("/select-client/<int:i>")
@req
def select_client(i): session["active_client_id"]=i; return redirect("/dashboard")

@app.route("/company")
@req
def company():
    r=conn().execute("SELECT * FROM clients WHERE id=?",(cid(),)).fetchone()
    return page("""<section><h2>Company / Invoice Profile</h2><form method="post" action="/company/save" class="grid"><input name="company_name" value="{{r.company_name or ''}}" placeholder="Company"><input name="phone" value="{{r.phone or ''}}" placeholder="Phone"><input name="gstin" value="{{r.gstin or ''}}" placeholder="GSTIN"><input name="pan" value="{{r.pan or ''}}" placeholder="PAN"><input name="state" value="{{r.state or ''}}" placeholder="State"><input name="state_code" value="{{r.state_code or ''}}" placeholder="State Code"><input name="address" value="{{r.address or ''}}" placeholder="Address"><input name="payment_terms" value="{{r.payment_terms or ''}}" placeholder="Payment Terms"><input name="footer_text" value="{{r.footer_text or ''}}" placeholder="Footer"><button>Save Profile</button></form></section>""",r=r)
@app.post("/company/save")
@req
def company_save():
    f=request.form; conn().execute("UPDATE clients SET company_name=?,phone=?,gstin=?,pan=?,state=?,state_code=?,address=?,payment_terms=?,footer_text=? WHERE id=?",(f.get("company_name"),f.get("phone"),f.get("gstin"),f.get("pan"),f.get("state"),f.get("state_code") or sc(f.get("gstin")),f.get("address"),f.get("payment_terms"),f.get("footer_text"),cid())); conn().commit(); return redirect("/company")

@app.route("/branches")
@req
def branches():
    rows=conn().execute("SELECT * FROM branches WHERE client_id=?",(cid(),)).fetchall()
    return page("""<section><h2>Branches</h2><form method="post" action="/branch/save" class="grid"><input name="branch_code" placeholder="Code"><input name="name" placeholder="Name"><input name="prefix" placeholder="Prefix"><button>Save Branch</button></form></section><section><table><tr><th>Code</th><th>Name</th><th>Prefix</th></tr>{% for r in rows %}<tr><td>{{r.branch_code}}</td><td>{{r.name}}</td><td>{{r.prefix}}</td></tr>{% endfor %}</table></section>""",rows=rows)
@app.post("/branch/save")
@req
def branch_save():
    f=request.form; conn().execute("INSERT INTO branches(client_id,branch_code,name,prefix) VALUES(?,?,?,?)",(cid(),f.get("branch_code"),f.get("name"),f.get("prefix"))); conn().commit(); return redirect("/branches")

@app.route("/masters")
@req
def masters():
    c=cid(); customers=conn().execute("SELECT * FROM customers WHERE client_id=? ORDER BY id DESC",(c,)).fetchall(); products=conn().execute("SELECT * FROM products WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<section><h2>Customer Master</h2><form method="post" action="/customer/save" class="grid"><input name="name" placeholder="Customer Name" required><input name="gstin" placeholder="GSTIN"><input name="pan" placeholder="PAN"><input name="phone" placeholder="Phone"><input name="email" placeholder="Email"><input name="state" placeholder="State"><input name="state_code" placeholder="State Code"><input name="due_days" value="15"><input name="address" placeholder="Bill To Address"><input name="shipping_name" placeholder="Ship To Name"><input name="shipping_address" placeholder="Ship To Address"><input name="shipping_state" placeholder="Ship To State"><input name="shipping_state_code" placeholder="Ship State Code"><button>Save Customer</button></form></section><section><h2>Product Master</h2><form method="post" action="/product/save" class="grid"><input name="name" placeholder="Product / Service" required><input name="hsn" placeholder="HSN"><input name="price" placeholder="Rate"><input name="gst" placeholder="GST"><input name="unit" value="Nos"><button>Save Product</button></form></section><section><h2>Customers</h2><table><tr><th>Name</th><th>GSTIN</th><th>Phone</th><th>Address</th></tr>{% for r in customers %}<tr><td>{{r.name}}</td><td>{{r.gstin}}</td><td>{{r.phone}}</td><td>{{r.address}}</td></tr>{% endfor %}</table></section><section><h2>Products</h2><table><tr><th>Name</th><th>HSN</th><th>Rate</th><th>GST</th></tr>{% for r in products %}<tr><td>{{r.name}}</td><td>{{r.hsn}}</td><td>₹{{r.price}}</td><td>{{r.gst}}%</td></tr>{% endfor %}</table></section>""",customers=customers,products=products)
@app.post("/customer/save")
@req
def customer_save():
    f=request.form; st=f.get("state_code") or sc(f.get("gstin")); conn().execute("INSERT INTO customers(client_id,name,gstin,pan,phone,email,state,state_code,address,shipping_name,shipping_address,shipping_state,shipping_state_code,due_days) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cid(),f.get("name"),f.get("gstin"),f.get("pan"),f.get("phone"),f.get("email"),f.get("state"),st,f.get("address"),f.get("shipping_name") or f.get("name"),f.get("shipping_address") or f.get("address"),f.get("shipping_state") or f.get("state"),f.get("shipping_state_code") or st,f.get("due_days") or 15)); conn().commit(); return redirect("/masters")
@app.post("/product/save")
@req
def product_save():
    f=request.form; conn().execute("INSERT INTO products(client_id,name,hsn,price,gst,unit) VALUES(?,?,?,?,?,?)",(cid(),f.get("name"),f.get("hsn"),fl(f.get("price")),fl(f.get("gst")),f.get("unit") or "Nos")); conn().commit(); return redirect("/masters")

@app.route("/roc")
@req
def roc():
    c=cid(); customers=conn().execute("SELECT * FROM customers WHERE client_id=?",(c,)).fetchall(); products=conn().execute("SELECT * FROM products WHERE client_id=?",(c,)).fetchall(); rocs=conn().execute("SELECT * FROM rate_contracts WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<script>function fillProduct(){const s=document.getElementById('product_id');const o=s.options[s.selectedIndex];document.getElementById('item_name').value=o.dataset.name||'';document.getElementById('hsn').value=o.dataset.hsn||'';document.getElementById('approved_rate').value=o.dataset.price||'';document.getElementById('gst').value=o.dataset.gst||'';document.getElementById('uom').value=o.dataset.unit||'Nos';}</script><section><h2>Rate Contract</h2><form method="post" action="/roc/save" class="grid"><select name="customer_id" required><option value="">Select Customer</option>{% for r in customers %}<option value="{{r.id}}">{{r.name}}</option>{% endfor %}</select><select id="product_id" name="product_id" onchange="fillProduct()"><option value="">Manual / Select Product</option>{% for p in products %}<option value="{{p.id}}" data-name="{{p.name}}" data-hsn="{{p.hsn}}" data-price="{{p.price}}" data-gst="{{p.gst}}" data-unit="{{p.unit}}">{{p.name}}</option>{% endfor %}</select><input id="item_name" name="item_name" placeholder="Item"><input id="hsn" name="hsn" placeholder="HSN"><input id="uom" name="uom" value="Nos"><input id="approved_rate" name="approved_rate" placeholder="Approved Rate"><input id="gst" name="gst" placeholder="GST"><input name="valid_from" type="date"><input name="valid_to" type="date"><input name="remarks" placeholder="Remarks"><button>Save ROC</button></form></section><section><h2>ROC List</h2><table><tr><th>Customer</th><th>Item</th><th>Rate</th><th>GST</th></tr>{% for r in rocs %}<tr><td>{{r.customer_name}}</td><td>{{r.item_name}}</td><td>₹{{r.approved_rate}}</td><td>{{r.gst}}%</td></tr>{% endfor %}</table></section>""",customers=customers,products=products,rocs=rocs)
@app.post("/roc/save")
@req
def roc_save():
    f=request.form; c=cid(); cu=conn().execute("SELECT * FROM customers WHERE id=?",(f.get("customer_id"),)).fetchone(); pr=conn().execute("SELECT * FROM products WHERE id=?",(f.get("product_id"),)).fetchone()
    conn().execute("INSERT INTO rate_contracts(client_id,customer_id,product_id,customer_name,item_name,hsn,uom,approved_rate,gst,valid_from,valid_to,status,remarks) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(c,f.get("customer_id"),f.get("product_id"),cu["name"] if cu else "",f.get("item_name") or (pr["name"] if pr else ""),f.get("hsn") or (pr["hsn"] if pr else ""),f.get("uom") or "Nos",fl(f.get("approved_rate")),fl(f.get("gst")) or (pr["gst"] if pr else 0),f.get("valid_from"),f.get("valid_to"),"Active",f.get("remarks"))); conn().commit(); return redirect("/roc")

@app.route("/invoices")
@req
def invoices():
    c=cid(); customers=conn().execute("SELECT * FROM customers WHERE client_id=?",(c,)).fetchall(); products=conn().execute("SELECT * FROM products WHERE client_id=?",(c,)).fetchall(); branches=conn().execute("SELECT * FROM branches WHERE client_id=?",(c,)).fetchall(); inv=conn().execute("SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<script>function fillInvProduct(){const s=document.getElementById('product_id');const o=s.options[s.selectedIndex];document.getElementById('rate').value=o.dataset.price||'';document.getElementById('gst').value=o.dataset.gst||'';}</script><section><h2>Create Invoice / Proforma / Quotation</h2><form method="post" action="/invoice/save" class="grid"><select name="invoice_type"><option>Tax Invoice</option><option>Proforma Invoice</option><option>Quotation</option></select><select name="branch_id">{% for b in branches %}<option value="{{b.id}}">{{b.name}}</option>{% endfor %}</select><input name="invoice_no" placeholder="Auto if blank"><input name="invoice_date" type="date"><input name="due_date" type="date"><select name="customer_id" required><option value="">Select Customer</option>{% for r in customers %}<option value="{{r.id}}">{{r.name}}</option>{% endfor %}</select><select id="product_id" name="product_id" onchange="fillInvProduct()" required><option value="">Select Product</option>{% for p in products %}<option value="{{p.id}}" data-price="{{p.price}}" data-gst="{{p.gst}}">{{p.name}}</option>{% endfor %}</select><input name="qty" value="1"><input id="rate" name="rate" placeholder="Rate"><input id="gst" name="gst" placeholder="GST"><button>Save Invoice</button></form></section><section><h2>Invoices</h2><table><tr><th>No</th><th>Type</th><th>Date</th><th>Customer</th><th>Total</th><th>Status</th><th>Action</th></tr>{% for i in inv %}<tr><td>{{i.invoice_no}}</td><td>{{i.invoice_type}}</td><td>{{i.invoice_date}}</td><td>{{i.customer_name}}</td><td>₹{{i.total}}</td><td>{{i.status}}</td><td><a class="btn" href="/invoice/{{i.id}}" target="_blank">Print/PDF</a> <a class="btn danger" href="/credit-note/create/{{i.id}}">Credit Note</a></td></tr>{% endfor %}</table></section>""",customers=customers,products=products,branches=branches,inv=inv)
@app.post("/invoice/save")
@req
def invoice_save():
    c=cid(); f=request.form; cu=conn().execute("SELECT * FROM customers WHERE id=? AND client_id=?",(f.get("customer_id"),c)).fetchone(); pr=conn().execute("SELECT * FROM products WHERE id=? AND client_id=?",(f.get("product_id"),c)).fetchone(); br=conn().execute("SELECT * FROM branches WHERE id=? AND client_id=?",(f.get("branch_id"),c)).fetchone()
    if not cu or not pr or not br: raise Exception("Customer/Product/Branch missing")
    qty=fl(f.get("qty"),1); rate=fl(f.get("rate")) or pr["price"]; gst=fl(f.get("gst")) or pr["gst"]; tax=qty*rate; ga=tax*gst/100; total=tax+ga
    no=f.get("invoice_no") or f"{br['prefix']}/{datetime.date.today().year}-{str(conn().execute('SELECT COUNT(*) c FROM invoices WHERE client_id=?',(c,)).fetchone()['c']+1).zfill(3)}"
    invdate=f.get("invoice_date") or today(); due=f.get("due_date") or invdate
    data={"customer_name":cu["name"],"bill_to_address":cu["address"],"ship_to_name":cu["shipping_name"] or cu["name"],"ship_to_address":cu["shipping_address"] or cu["address"],"items":[{"name":pr["name"],"hsn":pr["hsn"],"qty":qty,"rate":rate,"gst":gst,"taxable":tax,"gst_amount":ga,"total":total}]}
    conn().execute("INSERT INTO invoices(client_id,branch_id,invoice_type,invoice_no,invoice_date,due_date,customer_id,customer_name,taxable,gst_amount,total,status,invoice_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(c,br["id"],f.get("invoice_type"),no,invdate,due,cu["id"],cu["name"],tax,ga,total,"Unpaid",json.dumps(data))); conn().commit(); return redirect("/invoices")

@app.route("/invoice/<int:i>")
@req
def invoice_view(i):
    inv=conn().execute("SELECT * FROM invoices WHERE id=?",(i,)).fetchone(); client=conn().execute("SELECT * FROM clients WHERE id=?",(inv["client_id"],)).fetchone(); data=json.loads(inv["invoice_json"])
    return render_template_string("""<!DOCTYPE html><html><head><title>{{inv.invoice_no}}</title>"""+CSS+"""</head><body><div class="toolbar" style="text-align:right;padding:10px"><button onclick="window.print()">Print / Save PDF</button></div><section><div style="display:flex;justify-content:space-between;border-bottom:2px solid #123b63"><div><h1>{{client.company_name}}</h1><p><b>GSTIN:</b> {{client.gstin or '-'}}</p><p>{{client.address or '-'}}</p></div><div><h2>{{inv.invoice_type}}</h2><p><b>No:</b> {{inv.invoice_no}}</p><p><b>Date:</b> {{inv.invoice_date}}</p></div></div><div class="grid" style="grid-template-columns:1fr 1fr"><div><h3>Bill To</h3><b>{{data.customer_name}}</b><p>{{data.bill_to_address}}</p></div><div><h3>Ship To</h3><b>{{data.ship_to_name}}</b><p>{{data.ship_to_address}}</p></div></div><table><tr><th>#</th><th>Item</th><th>HSN</th><th>Qty</th><th>Rate</th><th>GST</th><th>Total</th></tr>{% for it in data["items"] %}<tr><td>{{loop.index}}</td><td>{{it.name}}</td><td>{{it.hsn}}</td><td>{{it.qty}}</td><td>₹{{it.rate}}</td><td>{{it.gst}}%</td><td>₹{{it.total}}</td></tr>{% endfor %}</table><h2 style="text-align:right">Grand Total: ₹{{inv.total}}</h2><p class="note">{{client.footer_text}}</p></section></body></html>""",inv=inv,client=client,data=data)

@app.route("/receipts")
@req
def receipts():
    c=cid(); inv=conn().execute("SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC",(c,)).fetchall(); rec=conn().execute("SELECT r.*,i.invoice_no FROM receipts r LEFT JOIN invoices i ON i.id=r.invoice_id WHERE r.client_id=? ORDER BY r.id DESC",(c,)).fetchall()
    return page("""<section><h2>Receipts</h2><form method="post" action="/receipt/save" class="grid"><select name="invoice_id">{% for i in inv %}<option value="{{i.id}}">{{i.invoice_no}} - {{i.customer_name}} - ₹{{i.total}}</option>{% endfor %}</select><input name="amount" placeholder="Amount"><input name="payment_mode" placeholder="Cash/UPI/Bank"><input name="payment_ref" placeholder="Payment Ref"><button>Save Receipt</button></form></section><section><table><tr><th>Receipt</th><th>Invoice</th><th>Amount</th><th>Mode</th></tr>{% for r in rec %}<tr><td>{{r.receipt_no}}</td><td>{{r.invoice_no}}</td><td>₹{{r.amount}}</td><td>{{r.payment_mode}}</td></tr>{% endfor %}</table></section>""",inv=inv,rec=rec)
@app.post("/receipt/save")
@req
def receipt_save():
    c=cid(); f=request.form; no=nextno("receipts","REC",c); conn().execute("INSERT INTO receipts(client_id,invoice_id,receipt_no,receipt_date,amount,payment_mode,payment_ref,remarks) VALUES(?,?,?,?,?,?,?,?)",(c,f.get("invoice_id"),no,today(),fl(f.get("amount")),f.get("payment_mode"),f.get("payment_ref"),"")); conn().execute("UPDATE invoices SET status='Paid' WHERE id=?",(f.get("invoice_id"),)); conn().commit(); return redirect("/receipts")

@app.route("/ledger")
@req
def ledger():
    c=cid(); inv=conn().execute("SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC",(c,)).fetchall(); rec=conn().execute("SELECT * FROM receipts WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<section><h2>Ledger</h2><h3>Invoices</h3><table><tr><th>No</th><th>Date</th><th>Customer</th><th>Total</th><th>Status</th></tr>{% for i in inv %}<tr><td>{{i.invoice_no}}</td><td>{{i.invoice_date}}</td><td>{{i.customer_name}}</td><td>₹{{i.total}}</td><td>{{i.status}}</td></tr>{% endfor %}</table><h3>Receipts</h3><table><tr><th>No</th><th>Date</th><th>Amount</th><th>Mode</th></tr>{% for r in rec %}<tr><td>{{r.receipt_no}}</td><td>{{r.receipt_date}}</td><td>₹{{r.amount}}</td><td>{{r.payment_mode}}</td></tr>{% endfor %}</table></section>""",inv=inv,rec=rec)

@app.route("/credit-notes")
@req
def credit_notes():
    c=cid(); notes=conn().execute("SELECT * FROM credit_notes WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<section><h2>Credit Notes</h2><table><tr><th>No</th><th>Date</th><th>Customer</th><th>Amount</th><th>Reason</th></tr>{% for n in notes %}<tr><td>{{n.credit_note_no}}</td><td>{{n.credit_note_date}}</td><td>{{n.customer_name}}</td><td>₹{{n.amount}}</td><td>{{n.reason}}</td></tr>{% endfor %}</table></section>""",notes=notes)
@app.route("/credit-note/create/<int:i>")
@req
def cn(i):
    inv=conn().execute("SELECT * FROM invoices WHERE id=?",(i,)).fetchone(); no=nextno("credit_notes","CN",inv["client_id"]); conn().execute("INSERT INTO credit_notes(client_id,invoice_id,credit_note_no,credit_note_date,customer_name,amount,reason) VALUES(?,?,?,?,?,?,?)",(inv["client_id"],i,no,today(),inv["customer_name"],inv["total"],"Invoice cancellation/adjustment")); conn().execute("UPDATE invoices SET status='Cancelled' WHERE id=?",(i,)); conn().commit(); return redirect("/credit-notes")

@app.route("/gst-gsp")
@req
def gst_gsp():
    c=cid(); inv=conn().execute("SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC",(c,)).fetchall(); tax=sum([r["taxable"] for r in inv]); gst=sum([r["gst_amount"] for r in inv]); total=sum([r["total"] for r in inv])
    return page("""<section><h2>GST/GSP Reports</h2><p>Use browser Print / Save as PDF.</p><table><tr><th>Taxable</th><th>CGST</th><th>SGST</th><th>IGST</th><th>Total GST</th><th>Total</th></tr><tr><td>₹{{tax}}</td><td>₹{{gst/2}}</td><td>₹{{gst/2}}</td><td>₹0</td><td>₹{{gst}}</td><td>₹{{total}}</td></tr></table></section><section><h2>GSTR-1 Sales Register</h2><table><tr><th>Invoice</th><th>Date</th><th>Customer</th><th>Taxable</th><th>GST</th><th>Total</th></tr>{% for i in inv %}<tr><td>{{i.invoice_no}}</td><td>{{i.invoice_date}}</td><td>{{i.customer_name}}</td><td>₹{{i.taxable}}</td><td>₹{{i.gst_amount}}</td><td>₹{{i.total}}</td></tr>{% endfor %}</table></section>""",inv=inv,tax=round(tax,2),gst=round(gst,2),total=round(total,2))
@app.route("/tally-sap")
@req
def tally_sap():
    c=cid(); inv=conn().execute("SELECT * FROM invoices WHERE client_id=? ORDER BY id DESC",(c,)).fetchall()
    return page("""<section><h2>Tally/SAP Export</h2><table><tr><th>Voucher Type</th><th>Invoice No</th><th>Date</th><th>Customer</th><th>Amount</th><th>Status</th></tr>{% for i in inv %}<tr><td>Sales</td><td>{{i.invoice_no}}</td><td>{{i.invoice_date}}</td><td>{{i.customer_name}}</td><td>{{i.total}}</td><td>{{i.status}}</td></tr>{% endfor %}</table></section>""",inv=inv)

if __name__=="__main__":
    app.run(host="0.0.0.0",port=int(os.environ.get("PORT",5000)),debug=True)
