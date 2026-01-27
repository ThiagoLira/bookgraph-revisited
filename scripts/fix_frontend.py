
from pathlib import Path

def main():
    path = Path("frontend/index.html")
    content = path.read_text()

    # The broken block we want to replace
    broken_snippet = """  for (let i = 0; i < manifest.length; i +=batchSize) { const batch=manifest.slice(i, i + batchSize); const
    results=await Promise.all(batch.map(f=> fetch(`${dataDir}/${f}`).then(r => r.json())));
    files.push(...results);
    }
    processData(files);

    document.getElementById("loading").style.display = "none";
    } catch (e) {
    console.error(e);
    document.getElementById("loading").textContent = "Error loading data: " + e.message;
    }
    }"""

    # The correct block
    correct_snippet = """      for (let i = 0; i < manifest.length; i += batchSize) {
        const batch = manifest.slice(i, i + batchSize);
        const results = await Promise.all(batch.map(f => fetch(`${dataDir}/${f}`).then(r => r.json())));
        files.push(...results);
      }
      processData(files);

      document.getElementById("loading").style.display = "none";
    } catch (e) {
      console.error(e);
      document.getElementById("loading").textContent = "Error loading data: " + e.message;
    }
  }"""

    if broken_snippet in content:
        new_content = content.replace(broken_snippet, correct_snippet)
        path.write_text(new_content)
        print("Frontend fixed successfully!")
    else:
        print("Could not find broken snippet. Dumping context around line 190:")
        lines = content.splitlines()
        for i, line in enumerate(lines[185:205], start=186):
            print(f"{i}: {line}")

if __name__ == "__main__":
    main()
