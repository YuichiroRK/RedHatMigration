import pandas as pd
import sqlite3
import os

def inicializar_base_datos():
    """
    Carga archivos fuente (Excel y CSV) desde la carpeta ./data 
    hacia la base de datos relacional migraciones.db.
    """
    ruta_db = 'migraciones.db'
    carpeta_datos = './data'
    
    # 1. Mapeo de Archivo Real -> Nombre de la Tabla en SQL
    # Nota: DATABASE ahora apunta al archivo .xlsx
    archivos_fuente = {
        'DATABASE.xlsx': 'DATABASE',
        'VMs.csv': 'VMs',
        'LOGS.csv': 'LOGS_VMS',
        'NOTIFICACIONES.csv': 'NOTIFICACIONES_CLIENTES',
        'DIRECTORIO_CLIENTE.csv': 'DIRECTORIO_CLIENTE',
        'ESTADO_VMS.csv': 'ESTADO_VMS',
        'TEAM_MIGRACION.csv': 'TEAM_MIGRACION'
    }
    
    conexion = sqlite3.connect(ruta_db)
    
    print("🚀 Iniciando carga masiva de datos...")
    print("-" * 40)
    
    for archivo, tabla in archivos_fuente.items():
        ruta_completa = os.path.join(carpeta_datos, archivo)
        
        if os.path.exists(ruta_completa):
            try:
                # 2. Lógica de lectura según la extensión del archivo
                if archivo.endswith('.xlsx'):
                    # Cargamos el Excel (por defecto la primera hoja)
                    df = pd.read_excel(ruta_completa, engine='openpyxl')
                else:
                    # Cargamos los CSV con codificación UTF-8 para evitar errores con tildes
                    df = pd.read_csv(ruta_completa, encoding='utf-8')
                
                # 3. Inyección a SQLite
                # 'replace' sobreescribe la tabla para tener siempre los datos más frescos del Excel/CSV
                df.to_sql(tabla, conexion, if_exists='replace', index=False)
                
                print(f"✅ {tabla:25} | Cargada ({len(df):4} registros) desde {archivo}")
                
            except Exception as e:
                print(f"❌ Error al procesar {archivo}: {e}")
        else:
            print(f"⚠️ Advertencia: No se encontró {archivo} en {carpeta_datos}")
            
    conexion.close()
    print("-" * 40)
    print("✨ ¡Base de datos 'migraciones.db' actualizada y lista!")

if __name__ == '__main__':
    # Creamos la carpeta data si no existe por si acaso
    if not os.path.exists('./data'):
        os.makedirs('./data')
        print("📁 Carpeta './data' creada. Coloca tus archivos allí.")
    
    inicializar_base_datos()