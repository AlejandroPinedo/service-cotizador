# src/get_handler.py
import json
import os
import boto3
import decimal

# Helper para convertir los números Decimal de DynamoDB a int/float
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o) if o % 1 else int(o)
        return super(DecimalEncoder, self).default(o)

# Inicialización de Clientes de AWS
COTIZACIONES_TABLE_NAME = os.environ['COTIZACIONES_TABLE_NAME']
dynamodb = boto3.resource('dynamodb')
cotizaciones_table = dynamodb.Table(COTIZACIONES_TABLE_NAME)

def handler(event, context):
    """
    Maneja la petición GET para obtener una cotización por su ID.
    """
    try:
        path_params = event.get('pathParameters', {})
        cotizacion_id = path_params.get('cotizacion_id')

        if not cotizacion_id:
            return {'statusCode': 400, 'body': json.dumps({'mensaje': 'Falta el ID de la cotización en la URL.'})}

        print(f"Buscando en DynamoDB el ID: {cotizacion_id}")
        response = cotizaciones_table.get_item(Key={'cotizacion_id': cotizacion_id})
        
        item = response.get('Item')
        if not item:
            return {'statusCode': 404, 'body': json.dumps({'mensaje': f"No se encontró una cotización con el ID: {cotizacion_id}"})}
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(item, cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"!!! ERROR INESPERADO: {str(e)} !!!")
        return {'statusCode': 500, 'body': json.dumps({'mensaje': f"Error interno del servidor: {str(e)}"}) }