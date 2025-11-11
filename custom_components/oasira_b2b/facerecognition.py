import os
import face_recognition
import cv2
from homeassistant.components.camera import async_get_image
from homeassistant.helpers.entity import Entity

class PersonFaceRecognitionSensor(Entity):
    """Sensor to perform face recognition."""

    def __init__(self, hass):
        self.hass = hass
        self._state = "Idle"

    async def async_update(self):
        """Update the sensor with the recognition result."""
        camera_entity_id = "camera.your_camera"
        image = await async_get_image(self.hass, camera_entity_id)

        # Save snapshot
        snapshot_path = "/config/www/snapshot.jpg"
        with open(snapshot_path, "wb") as file:
            file.write(image.content)

        # Perform face recognition
        person_dir = "/config/www/person_images"
        known_faces = []
        known_names = []

        for filename in os.listdir(person_dir):
            filepath = os.path.join(person_dir, filename)
            if filepath.endswith(".jpg") or filepath.endswith(".png"):
                image = face_recognition.load_image_file(filepath)
                encodings = face_recognition.face_encodings(image)
                if encodings:
                    known_faces.append(encodings[0])
                    known_names.append(os.path.splitext(filename)[0])

        # Load snapshot for recognition
        snapshot_image = face_recognition.load_image_file(snapshot_path)
        unknown_encodings = face_recognition.face_encodings(snapshot_image)

        for unknown_encoding in unknown_encodings:
            results = face_recognition.compare_faces(known_faces, unknown_encoding)
            if True in results:
                match_index = results.index(True)
                self._state = known_names[match_index]
                return

        self._state = "Unknown"

    @property
    def state(self):
        return self._state

    @property
    def name(self):
        return "Person Face Recognition"