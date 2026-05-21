import sys
import os

# Forza encoding UTF-8 per caratteri terminale Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# Aggiunge directory corrente al path di sistema
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.diagnostics import FeatureDiagnostics

def main():
    print("=" * 80)
    print(" 🔬 CERTIFICATO DI INTERPRETABILITÀ AI — PIPELINE SHAP ATTRIBUTION")
    print("=" * 80)
    
    try:
        diagnostics = FeatureDiagnostics()
        report = diagnostics.run_diagnostics()
        
        # Stampa summary delle feature
        print("\n" + "=" * 80)
        print(" 📊 CLASSIFICAZIONE STRUTTURALE DELLE FEATURE & RACCOMANDAZIONI")
        print("=" * 80)
        print(f"{'Feature':<20} | {'Classificazione':<20} | {'Attribution (T)':<15} | {'Attribution (R)':<15}")
        print("-" * 80)
        
        anomalies = report["anomalies"]
        for feat, data in anomalies.items():
            t_imp = data["trending_importance"]
            r_imp = data["ranging_importance"]
            cls = data["classification"]
            
            # Formattazione premium dei colori terminale
            if cls == "STABLE_DRIVER":
                cls_str = "🟢 STABLE DRIVER"
            elif cls == "REGIME_SPECIALIST":
                cls_str = "🔵 REGIME SPEC"
            elif cls == "POTENTIAL_OVERFIT":
                cls_str = "⚠️ OVERFIT COND"
            elif cls == "NOISY":
                cls_str = "❌ NOISY/UNSTABLE"
            else:
                cls_str = "⚪ NEUTRAL"
                
            print(f"{feat:<20} | {cls_str:<20} | {t_imp*100:<13.3f}% | {r_imp*100:<13.3f}%")
            
        print("\n📝 DETTAGLIO CONSIGLI QUANTITATIVI DI OTTIMIZZAZIONE:")
        for feat, data in anomalies.items():
            cls = data["classification"]
            if cls in ["POTENTIAL_OVERFIT", "NOISY"]:
                icon = "⚠️" if cls == "POTENTIAL_OVERFIT" else "❌"
                print(f"  {icon} {feat:<18}: {data['reason']}")
                print(f"     -> Azione: {data['action']}")
                
        print("=" * 80 + "\n")
        print("🎉 Pipeline di analisi terminato con successo!")
        print("   Per visualizzare i grafici interattivi avanzati, avvia il dashboard:")
        print("   >>> streamlit run dashboard.py\n")
        
    except Exception as e:
        print(f"❌ Errore critico nel pipeline diagnostico: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
