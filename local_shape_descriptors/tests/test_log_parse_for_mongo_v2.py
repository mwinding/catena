import re
import json
from tqdm import tqdm

from bson import ObjectId


def extract_info(line):
    command_match = re.search(r'pymongo\.command DEBUG.*?({.*})', line)
    if not command_match:
        return None

    try:
        outer_command = json.loads(command_match.group(1))
        # print(type(outer_command))
        # inner_command = outer_command['command']
        inner_command = json.loads(outer_command['command'])

        if 'documents' in inner_command and len(inner_command['documents']) > 0:
            doc = inner_command['documents'][0]

        return {
            'block_id': doc.get('block_id'),
            'read_roi': doc.get('read_roi'),
            'write_roi': doc.get('write_roi'),
            'start': doc.get('start'),
            'duration': doc.get('duration'),
            '_id': doc.get('_id', {}).get('$oid')
        }
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
    except KeyError as e:
        # print(f"Key not found: {e}")
        pass

    return None


def process_log_file(file_path):
    results = []
    with open(file_path, 'r') as file:
        for line in tqdm(file):
            result = extract_info(line.strip())
            if result:
                results.append(result)
    return results


def save_to_json(data, json_output_file):
    # Append the batch of data to the JSON file
    with open(json_output_file, 'w') as f:
        for entry in data:
            json.dump(entry, f)
            f.write('\n')  # Each document on a new line (for easier MongoDB loading)


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


# Example usage
log_file_path = '/media/samia/DATA/ark/connexion/very_imp_inference_logs_neptune/predict_scan_logs_2024-05-19 08:42:19.642034.txt'
json_output_file = '/media/samia/DATA/ark/connexion/very_imp_inference_logs_neptune/extracted_predict_scan_logs_2024-05-19 08:42:19.642034.txt'
extracted_info = process_log_file(log_file_path)

# Print the first few results
for i, result in enumerate(extracted_info[:5]):  # Print first 5 results
    print(f"\nEntry {i + 1}:")
    print(f"Block ID: {result['block_id']}")
    print(f"Read ROI: {result['read_roi']}")
    print(f"Write ROI: {result['write_roi']}")
    print(f"Start: {result['start']}")
    print(f"Duration: {result['duration']}")
    print(f"ID: {result['_id']}")

print(f"\nTotal entries processed: {len(extracted_info)}")

# Save to JSON to load it back up in a mongoDB
save_to_json(extracted_info, json_output_file)

# Load to mongo
# Later, you can load the JSON file into MongoDB using this function:
# mongo_uri = "mongodb://localhost:27017/"
# db_name = "log_database"
# collection_name = "log_entries"
# load_json_to_mongo(json_output_file, mongo_uri, db_name, collection_name)
