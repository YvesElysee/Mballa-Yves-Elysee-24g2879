from flask import Flask, render_template, request, redirect
import pandas as pd
import numpy as np
import sqlite3
import os
from datetime import datetime
import json

app = Flask(__name__)

# Déplace l'appel ici, hors du bloc "if __name__ == '__main__':"
def init_db():
    conn = sqlite3.connect(db_path)
    conn.execute('''CREATE TABLE IF NOT EXISTS collecte 
        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
         date TEXT, secteur TEXT, indicateur TEXT, valeur REAL, 
         unite TEXT, region TEXT, ville TEXT)''')
    conn.commit()
    conn.close()

# Appel automatique au démarrage global
init_db()

# --- LOGIQUE DE CALCUL STATISTIQUE ---
def compute_sector_stats(sdf):
    if sdf.empty: 
        return None
        
    v = sdf['valeur']
    n = len(sdf)
    
    # 1. Statistiques de base
    moyenne = v.mean()
    variance = v.var(ddof=0) if n > 1 else 0 # ddof=0 pour la variance de population en TP
    
    # 2. Calcul des fréquences et cumuls (ni, fi, ECC, ECD)
    # On regroupe par indicateur pour voir la répartition des types de données
    freq_df = sdf.groupby('indicateur').agg(ni=('valeur', 'count')).reset_index()
    freq_df['fi'] = (freq_df['ni'] / n * 100).round(2)
    freq_df['ECC'] = freq_df['ni'].cumsum()
    freq_df['ECD'] = n - freq_df['ni'].cumsum().shift(1).fillna(0)
    
    # 3. Préparation Régression Linéaire (y = ax + b)
    x = np.arange(n)
    y = v.values
    reg_line = []
    reg_txt = "Données insuffisantes (min 2)"
    
    if n > 1:
        try:
            slope, intercept = np.polyfit(x, y, 1)
            reg_line = (slope * x + intercept).tolist()
            reg_txt = f"y = {slope:.2f}x {'+' if intercept >= 0 else '-'} {abs(intercept):.2f}"
        except:
            reg_txt = "Erreur de calcul"

    # 4. Structure pour le Frontend (Chart.js)
    return {
        'count': n,
        'moyenne': round(moyenne, 2),
        'variance': round(variance, 2),
        'std': round(np.sqrt(variance), 2),
        'regression_txt': reg_txt,
        'indices': [f"n{i+1}" for i in range(n)],
        'valeurs': v.tolist(),
        'moyenne_evol': v.expanding().mean().round(2).tolist(), # Graphe de moyenne mobile
        'reg_line': reg_line, # Graphe régression
        'labels_freq': freq_df['indicateur'].tolist(),
        'data_fi': freq_df['fi'].tolist(), # Graphe fréquences
        'data_ecc': freq_df['ECC'].tolist(), # Graphe ECC
        'data_ecd': freq_df['ECD'].tolist(), # Graphe ECD
        'table': freq_df.to_dict(orient='records')
    }

# --- ROUTES FLASK ---

@app.route('/')
def index():
    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query("SELECT * FROM collecte ORDER BY id ASC", conn)
    conn.close()

    dashboard_data = {
        "is_empty": df.empty,
        "global": {"total": 0, "labels": [], "pourcentages": []},
        "secteurs": {"Sante": None, "Agri": None, "Eco": None}
    }

    if not df.empty:
        # Données du Doughnut Chart Global
        repartition_globale = df['secteur'].value_counts(normalize=True) * 100
        dashboard_data["global"]["total"] = len(df)
        dashboard_data["global"]["labels"] = repartition_globale.index.tolist()
        dashboard_data["global"]["pourcentages"] = repartition_globale.round(1).tolist()
        
        # Calcul des stats pour chaque secteur
        for secteur in ["Sante", "Agri", "Eco"]:
            sdf = df[df['secteur'] == secteur]
            if not sdf.empty:
                dashboard_data["secteurs"][secteur] = compute_sector_stats(sdf)

    return render_template('index.html', data=json.dumps(dashboard_data))

@app.route('/add', methods=['POST'])
def add():
    secteur = request.form.get('secteur')
    # Récupère l'indicateur spécifique (ind_Sante, ind_Agri, ou ind_Eco)
    ind = request.form.get(f'ind_{secteur}')
    val = request.form.get('valeur')
    unite = request.form.get('unite')
    region = request.form.get('region')
    ville = request.form.get('ville')
    
    if val:
        try:
            conn = sqlite3.connect(db_path)
            conn.execute("""INSERT INTO collecte (date, secteur, indicateur, valeur, unite, region, ville) 
                            VALUES (?,?,?,?,?,?,?)""",
                         (datetime.now().strftime("%d/%m %H:%M"), 
                          secteur, ind, float(val), unite, region, ville))
            conn.commit()
            conn.close()
        except ValueError:
            pass # Gérer l'erreur si la valeur n'est pas un nombre
            
    return redirect('/')

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
