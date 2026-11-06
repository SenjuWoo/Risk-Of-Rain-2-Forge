// Reads the referenced assemblies out of a compiled mod without loading or executing it.
// System.Reflection.Metadata parses the PE file as data, so an untrusted DLL is never resolved or run.
// Output is one JSON object on stdout: { assembly, version, references: [{ name, version }] }

using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Text.Json;

if (args.Length != 1 || !File.Exists(args[0]))
{
    Console.Error.WriteLine("usage: asmrefs <assembly.dll>");
    return 2;
}

using var stream = File.OpenRead(args[0]);
using var pe = new PEReader(stream);
if (!pe.HasMetadata)
{
    Console.Error.WriteLine("not a managed assembly");
    return 3;
}

MetadataReader reader = pe.GetMetadataReader();
string name = reader.IsAssembly ? reader.GetString(reader.GetAssemblyDefinition().Name) : "";
var version = reader.IsAssembly
    ? reader.GetAssemblyDefinition().Version.ToString()
    : "";

var references = new List<object>();
foreach (AssemblyReferenceHandle handle in reader.AssemblyReferences)
{
    AssemblyReference reference = reader.GetAssemblyReference(handle);
    references.Add(new { name = reader.GetString(reference.Name), version = reference.Version.ToString() });
}

Console.WriteLine(JsonSerializer.Serialize(new { assembly = name, version, references }));
return 0;
