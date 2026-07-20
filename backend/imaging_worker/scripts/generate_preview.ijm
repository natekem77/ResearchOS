arg = getArgument();
parts = split(arg, "|");
input = replace(parts[0], "input=", "");
output = replace(parts[1], "output=", "");

open(input);
run("Duplicate...", "title=preview");
run("Enhance Contrast", "saturated=0.35");
saveAs("PNG", output);
close("*");
run("Quit");
