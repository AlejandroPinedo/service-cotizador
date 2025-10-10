# src/approve_handler.py
import json
import os
import boto3
import decimal

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, decimal.Decimal):
            return float(o) if o % 1 else int(o)
        return super(DecimalEncoder, self).default(o)

COTIZACIONES_TABLE_NAME = os.environ['COTIZACIONES_TABLE_NAME']
dynamodb = boto3.resource('dynamodb')
cotizaciones_table = dynamodb.Table(COTIZACIONES_TABLE_NAME)

def handler(event, context):
    """
    Maneja la petición POST para cambiar el estado de una cotización a 'APROBADA'.
    """
    try:
        path_params = event.get('pathParameters', {})
        cotizacion_id = path_params.get('cotizacion_id')

        if not cotizacion_id:
            return {'statusCode': 400, 'body': json.dumps({'mensaje': 'Falta el ID de la cotización en la URL.'})}

        print(f"Aprobando en DynamoDB el ID: {cotizacion_id}")
        updated_item = cotizaciones_table.update_item(
            Key={'cotizacion_id': cotizacion_id},
            UpdateExpression="SET #st = :estado_val",
            ExpressionAttributeNames={"#st": "estado"},
            ExpressionAttributeValues={":estado_val": "APROBADA"},
            ReturnValues="ALL_NEW"
        )
        
        return {
            'statusCode': 200,
            'headers': {'Content-Type': 'application/json'},
            'body': json.dumps(updated_item.get('Attributes'), cls=DecimalEncoder)
        }

    except Exception as e:
        print(f"!!! ERROR INESPERADO: {str(e)} !!!")
        return {'statusCode': 500, 'body': json.dumps({'mensaje': f"Error interno del servidor: {str(e)}"}) }