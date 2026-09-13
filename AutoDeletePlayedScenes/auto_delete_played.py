import sys
import json
import subprocess

# Auto-Installation der benötigten Bibliothek, falls nicht vorhanden
try:
    import stashapi.log as log
    from stashapi.stashapp import StashInterface
except ImportError:
    print("Benötigte Bibliothek 'stashapp-tools' nicht gefunden. Starte automatische Installation...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "stashapp-tools"])
    except Exception:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "stashapp-tools"])
        
    import stashapi.log as log
    from stashapi.stashapp import StashInterface

# Stash übergibt bei Task-Ausführung Daten via stdin
try:
    json_input = json.loads(sys.stdin.read())
    FRAGMENT_SERVER = json_input["server_connection"]
except Exception as e:
    log.error(f"Fehler beim Lesen der Plugin-Inputs: {e}")
    sys.exit(1)

# Verbindung zu Stash aufbauen
stash = StashInterface(FRAGMENT_SERVER)

log.info("Starte Auto-Delete Plugin (Play-Count >= 2)...")

# GraphQL Query: Finde alle Szenen mit play_count > 1
query_find_scenes = """
query FindScenes($filter: FindFilterType, $scene_filter: SceneFilterType) {
  findScenes(filter: $filter, scene_filter: $scene_filter) {
    count
    scenes {
      id
      title
      play_count
    }
  }
}
"""

# GraphQL Mutation: Szene unwiderruflich löschen (Datei + Thumbnails + DB)
mutation_destroy_scene = """
mutation SceneDestroy($input: SceneDestroyInput!) {
  sceneDestroy(input: $input)
}
"""

destroyed_count = 0
total_scenes = None

# Filter-Kriterium: IntCriterionInput für play_count > 1 (entspricht >= 2)
scene_filter = {
    "play_count": {
        "value": 1,
        "modifier": "GREATER_THAN"
    }
}

# Pagination-Logik: Da wir löschen, rücken die restlichen passenden Szenen 
# automatisch auf Seite 1 nach.
while True:
    variables = {
        "filter": {
            "page": 1,
            "per_page": 100,
            "sort": "created_at",
            "direction": "DESC"
        },
        "scene_filter": scene_filter
    }
    
    try:
        result = stash.callGQL(query_find_scenes, variables)
        if not result or "findScenes" not in result:
            log.error("GraphQL-Antwort fehlerhaft oder leer.")
            break
            
        find_scenes_data = result["findScenes"]
        if total_scenes is None:
            total_scenes = find_scenes_data["count"]
            log.info(f"Insgesamt {total_scenes} Szenen mit Play-Count >= 2 gefunden.")
            if total_scenes == 0:
                break
                
        scenes = find_scenes_data["scenes"]
        if not scenes:
            break
            
        failed_deletes = False
        for scene in scenes:
            scene_id = scene["id"]
            title = scene.get("title", "Unbekannter Titel")
            play_count = scene.get("play_count", 0)
            
            log.info(f"Lösche Szene: '{title}' (ID: {scene_id}, Plays: {play_count})")
            
            destroy_variables = {
                "input": {
                    "id": str(scene_id),
                    "delete_file": True,
                    "delete_generated": True
                }
            }
            
            try:
                stash.callGQL(mutation_destroy_scene, destroy_variables)
                destroyed_count += 1
            except Exception as e:
                log.error(f"Fehler beim Löschen von Szene {scene_id}: {e}")
                failed_deletes = True
                
        if failed_deletes:
            log.error("Löschvorgang abgebrochen, da Fehler auftraten.")
            break
            
    except Exception as e:
        log.error(f"Fehler bei der Datenbankabfrage: {e}")
        break

log.info(f"Erfolgreich {destroyed_count} Szenen komplett entfernt.")
