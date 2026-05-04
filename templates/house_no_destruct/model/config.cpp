class CfgPatches
{
	class CLASSNAME
	{
		units[]={ "CLASSNAME" };
		weapons[]={};
		requiredVersion=0.1;
		requiredAddons[]={ "DZ_Data" };
	};
};

CFGMODS
class CfgVehicles
{
	class HouseNoDestruct;
	class CLASSNAME: HouseNoDestruct
	{
		scope=2;
		displayName="CHANGE ME";
		model="MODELPATH";
		forceFarBubble="true";
		slopeTolerance=0.2;
		carveNavmesh=1;
		ANIMSOURCES
		class DamageSystem
		{
			class GlobalHealth
			{
				class Health
				{
					hitpoints=1000;
				};
			};
			class GlobalArmor
			{
				class Projectile
				{
					class Health { damage=0; };
					class Blood { damage=0; };
					class Shock { damage=0; };
				};
				class Melee
				{
					class Health { damage=0; };
					class Blood { damage=0; };
					class Shock { damage=0; };
				};
			};
		};
	};
};
