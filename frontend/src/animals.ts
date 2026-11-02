/** Animal catalogue for the character picker. Any animal not listed can still be typed in. */
export interface AnimalGroup {
  id: string;
  label: string;
  icon: string;
  animals: [name: string, emoji?: string][];
}

export const ANIMAL_GROUPS: AnimalGroup[] = [
  {
    id: "wild", label: "Wild mammals", icon: "🦁",
    animals: [
      ["Lion", "🦁"], ["Lion cub", "🦁"], ["Lioness", "🦁"], ["Tiger", "🐯"], ["Tiger cub", "🐯"], ["White tiger", "🐯"], ["Leopard", "🐆"],
      ["Cheetah", "🐆"], ["Jaguar", "🐆"], ["Snow leopard", "🐆"], ["Black panther", "🐆"], ["Lynx"], ["Puma"], ["Bobcat"],
      ["Elephant", "🐘"], ["Baby elephant", "🐘"], ["Giraffe", "🦒"], ["Zebra", "🦓"], ["Rhinoceros", "🦏"], ["Hippopotamus", "🦛"],
      ["Gorilla", "🦍"], ["Chimpanzee"], ["Orangutan", "🦧"], ["Monkey", "🐒"], ["Baboon"], ["Langur", "🐒"], ["Lemur"], ["Sloth", "🦥"],
      ["Bear", "🐻"], ["Brown bear", "🐻"], ["Black bear", "🐻"], ["Sloth bear", "🐻"], ["Polar bear", "🐻‍❄️"], ["Panda", "🐼"],
      ["Red panda"], ["Koala", "🐨"], ["Kangaroo", "🦘"], ["Wallaby", "🦘"], ["Wombat"], ["Platypus"], ["Wolf", "🐺"], ["Fox", "🦊"],
      ["Arctic fox", "🦊"], ["Fennec fox", "🦊"], ["Jackal"], ["Hyena"], ["Deer", "🦌"], ["Spotted deer", "🦌"], ["Reindeer", "🦌"],
      ["Moose"], ["Antelope"], ["Blackbuck"], ["Gazelle"], ["Nilgai"], ["Bison", "🦬"], ["Wild buffalo", "🐃"], ["Gaur"],
      ["Wild boar", "🐗"], ["Squirrel", "🐿️"], ["Chipmunk", "🐿️"], ["Hedgehog", "🦔"], ["Porcupine"], ["Raccoon", "🦝"], ["Skunk", "🦨"],
      ["Otter", "🦦"], ["Beaver", "🦫"], ["Badger", "🦡"], ["Meerkat"], ["Mongoose"], ["Armadillo"], ["Anteater"], ["Pangolin"],
      ["Bat", "🦇"], ["Camel", "🐫"], ["Llama", "🦙"], ["Alpaca", "🦙"], ["Yak"], ["Mole"], ["Okapi"], ["Tapir"], ["Wild rabbit", "🐇"],
      ["Hare", "🐇"], ["Field mouse", "🐁"],
    ],
  },
  {
    id: "farm", label: "Farm & domestic", icon: "🐄",
    animals: [
      ["Cow", "🐄"], ["Calf", "🐄"], ["Bull", "🐂"], ["Ox", "🐂"], ["Water buffalo", "🐃"], ["Goat", "🐐"], ["Baby goat", "🐐"],
      ["Sheep", "🐑"], ["Lamb", "🐑"], ["Ram", "🐏"], ["Horse", "🐎"], ["Foal", "🐎"], ["Pony", "🐎"], ["Donkey"], ["Mule"],
      ["Pig", "🐖"], ["Piglet", "🐷"], ["Hen", "🐔"], ["Rooster", "🐓"], ["Chick", "🐤"], ["Duck", "🦆"], ["Duckling", "🐥"],
      ["Goose", "🪿"], ["Turkey", "🦃"], ["Farm rabbit", "🐇"], ["Guinea fowl"], ["Camel (farm)", "🐫"], ["Farm dog", "🐕"], ["Barn cat", "🐈"],
    ],
  },
  {
    id: "pets", label: "Pets, dogs & cats", icon: "🐶",
    animals: [
      ["Dog", "🐕"], ["Puppy", "🐶"], ["Labrador", "🐕"], ["Golden Retriever", "🐕"], ["German Shepherd", "🐕‍🦺"], ["Husky", "🐕"],
      ["Beagle", "🐕"], ["Pug", "🐶"], ["Dalmatian", "🐕"], ["Pomeranian", "🐶"], ["Bulldog", "🐶"], ["Indian street dog", "🐕"],
      ["Rajapalayam dog", "🐕"], ["Chippiparai dog", "🐕"], ["Dachshund", "🐕"], ["Poodle", "🐩"],
      ["Cat", "🐈"], ["Kitten", "🐱"], ["Persian cat", "🐱"], ["Siamese cat", "🐱"], ["Black cat", "🐈‍⬛"], ["Orange tabby cat", "🐱"],
      ["Pet rabbit", "🐰"], ["Hamster", "🐹"], ["Guinea pig"], ["Pet mouse", "🐭"], ["Ferret"], ["Goldfish", "🐠"], ["Pet turtle", "🐢"],
      ["Budgie", "🦜"], ["Cockatiel", "🦜"], ["Canary", "🐤"], ["Love birds", "🦜"],
    ],
  },
  {
    id: "birds", label: "Birds", icon: "🦅",
    animals: [
      ["Eagle", "🦅"], ["Hawk"], ["Falcon"], ["Owl", "🦉"], ["Baby owl", "🦉"], ["Parrot", "🦜"], ["Macaw", "🦜"], ["Cockatoo", "🦜"],
      ["Peacock", "🦚"], ["Sparrow"], ["Crow", "🐦‍⬛"], ["Pigeon"], ["Dove", "🕊️"], ["Kingfisher"], ["Woodpecker"], ["Hummingbird"],
      ["Robin"], ["Bluebird"], ["Cardinal"], ["Myna"], ["Cuckoo"], ["Koel"], ["Bulbul"], ["Hornbill"], ["Toucan"], ["Flamingo", "🦩"],
      ["Swan", "🦢"], ["Crane"], ["Stork"], ["Heron"], ["Pelican"], ["Seagull"], ["Penguin", "🐧"], ["Baby penguin", "🐧"],
      ["Ostrich"], ["Emu"], ["Kiwi bird"], ["Vulture"], ["Kite"], ["Weaver bird"], ["Quail"], ["Partridge"], ["Swallow"],
      ["Magpie"], ["Puffin"], ["Albatross"], ["Hoopoe"], ["Duck (wild)", "🦆"], ["Little bird", "🐦"],
    ],
  },
  {
    id: "water", label: "Ocean & water", icon: "🐬",
    animals: [
      ["Dolphin", "🐬"], ["Whale", "🐋"], ["Blue whale", "🐳"], ["Orca"], ["Shark", "🦈"], ["Octopus", "🐙"], ["Squid", "🦑"],
      ["Jellyfish", "🪼"], ["Sea turtle", "🐢"], ["Seal", "🦭"], ["Sea lion", "🦭"], ["Walrus"], ["Narwhal"], ["Manatee"],
      ["Clownfish", "🐠"], ["Tropical fish", "🐠"], ["Pufferfish", "🐡"], ["Starfish"], ["Seahorse"], ["Crab", "🦀"], ["Lobster", "🦞"],
      ["Shrimp", "🦐"], ["Manta ray"], ["Stingray"], ["Salmon"], ["Catfish"], ["Eel"], ["Koi fish", "🐟"],
    ],
  },
  {
    id: "reptiles", label: "Reptiles & amphibians", icon: "🐊",
    animals: [
      ["Crocodile", "🐊"], ["Alligator", "🐊"], ["Snake", "🐍"], ["Cobra", "🐍"], ["Python", "🐍"], ["Lizard", "🦎"], ["Chameleon", "🦎"],
      ["Gecko", "🦎"], ["Iguana", "🦎"], ["Komodo dragon", "🦎"], ["Tortoise", "🐢"], ["Turtle", "🐢"], ["Frog", "🐸"], ["Tree frog", "🐸"],
      ["Toad", "🐸"], ["Salamander"], ["Axolotl"],
    ],
  },
  {
    id: "insects", label: "Insects & small creatures", icon: "🦋",
    animals: [
      ["Butterfly", "🦋"], ["Honeybee", "🐝"], ["Ant", "🐜"], ["Ladybug", "🐞"], ["Dragonfly"], ["Grasshopper", "🦗"], ["Firefly"],
      ["Caterpillar", "🐛"], ["Spider", "🕷️"], ["Snail", "🐌"], ["Beetle", "🪲"], ["Cricket", "🦗"], ["Moth"], ["Earthworm", "🪱"],
      ["Scorpion", "🦂"],
    ],
  },
  {
    id: "prehistoric", label: "Dinosaurs & prehistoric", icon: "🦖",
    animals: [
      ["T-rex", "🦖"], ["Triceratops", "🦕"], ["Stegosaurus", "🦕"], ["Brachiosaurus", "🦕"], ["Velociraptor", "🦖"],
      ["Pterodactyl"], ["Woolly mammoth", "🦣"], ["Sabre-toothed cat"], ["Baby dinosaur", "🦕"],
    ],
  },
];

export const ALL_ANIMALS = ANIMAL_GROUPS.flatMap((g) => g.animals.map(([name, emoji]) => ({ name, emoji: emoji ?? g.icon, group: g.id })));
