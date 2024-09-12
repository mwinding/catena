import re
import json
from tqdm import tqdm
import argparse
from bson import ObjectId


def load_json_to_mongo(json_file_path, mongo_uri, db_name, collection_name):
    from pymongo import MongoClient

    # Set up MongoDB connection
    client = MongoClient(mongo_uri)
    db = client[db_name]
    collection = db[collection_name]

    # Read JSON file and insert into MongoDB
    with open(json_file_path, 'r') as f:
        for line in f:
            document = json.loads(line)
            document['_id'] = ObjectId(document['_id'])  # Convert _id back to ObjectId
            collection.insert_one(document)

    print(f"Data inserted successfully into {db_name}.{collection_name}")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("-lf", "--logfile", help="/Path/to/your/extracted/logfile.txt")
    args = parser.parse_args()
    # this was extracted from the logs
    json_output_file = args.logfile #'/net/ark/scratch/smohinta/connexion/very_imp_inference_logs_neptune/extracted_predict_scan_logs_2024-05-19 08:42:19.642034.txt'

    # Load to mongo
    # Later, you can load the JSON file into MongoDB using this function:
    mongo_uri = "mongodb://localhost:27017/"
    db_name = "lsd_predictions_parallel" # name of your db: is generally lsd_predictions_parallel
    collection_name = "neptuneS0_MTLSD_predicted_affs" # name of your collection: should be the name of your input zarr file
    load_json_to_mongo(json_output_file, mongo_uri, db_name, collection_name)
