// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#ifndef VIEWFINDER_PHYSICS_MODEL_H
#define VIEWFINDER_PHYSICS_MODEL_H

#import <list>
#import "Vector.h"
#import "WallTime.h"

////
// Physics model for simulating spring and friction accelerations.
//
//  Derived from: http://gafferongames.com/game-physics/integration-basics/

class PhysicsModel {
 public:
  PhysicsModel();
  virtual ~PhysicsModel() {}

  void Reset();

  void Reset(const Vector2f& location, const Vector2f& velocity);

  const Vector2f& position() const { return state_.p; }
  void set_position(const Vector2f& p) { state_.p = p; }
  const Vector2f& velocity() const { return state_.v; }
  void set_velocity(const Vector2f& v) { state_.v = v; }

  // Sets "location" according to current accelerations at time "now"
  // and existing state of the model.
  // Returns whether the system has achieved equilibrium; that is,
  // velocity is 0 and location is unchanged.
  bool RunModel(Vector2f* prev_loc, Vector2f* new_loc, WallTime now=0);

  // This model applies accelerations to an object whose state is represented
  // by position and velocity.
  struct State {
    Vector2f p;  // position
    Vector2f v;  // velocity
  };
  typedef Vector2f (^AccelerationFunc)(const State& state, double t);
  typedef Vector2f (^AccelerationFilter)(const State& state, double t, const Vector2f& a);
  typedef Vector2f (^LocationFunc)(const State& state, double t);
  typedef bool (^ExitConditionFunc)(State* state, const State& prev_state, double t, const Vector2f& a);

  // Specifies a fixed location.
  static LocationFunc StaticLocation(const Vector2f& spring_loc);

  // Spring forces pull towards the location of the spring with varying
  // forces and include a dampening function to slow the approach velocity
  // to 0 as the object reaches the spring.

  // A totally customizable spring.
  void AddSpring(LocationFunc spring_loc, float spring_force, float damp_force);

  // The default spring takes about 1s to pull an object from anywhere on screen.
  void AddDefaultSpring(LocationFunc spring_loc);

  // Adds a spring which takes 550-600ms to pull an object from anywhere on screen.
  void AddQuickSpring(LocationFunc spring_loc);

  // Adds a spring that takes about 1.5s to pull an object from anywhere on screen.
  void AddSlowSpring(LocationFunc spring_loc);

  // Adds a spring which takes 350-400ms to pull an object from anywhere on screen.
  void AddVeryQuickSpring(LocationFunc spring_loc);

  // Add a spring force (acceleration = -kx, where k is spring force constant
  // and x is distance between spring and object). Also add a dampening force,
  // (acceleration = -bv, where b is the dampening factor and v is the velocity).
  void AddSpringWithDampening(LocationFunc spring_loc,
                              const float spring_force,
                              const float dampening_force);

  // Adds a custom acceleration function.
  void AddAccelerationFunction(AccelerationFunc func);

  // Adds a deceleration opposite the current velocity, proportional
  // to the release coefficient of friction.
  static const float kFrictionCoeff_;
  void AddReleaseDeceleration();

  // Adds a filter to be applied to the output of all acceleration
  // functions.  Multiple filters may be added and are applied
  // successively to first the output of all acceleration functions
  // and then to the output of each filter in turn.
  void AddAccelerationFilter(AccelerationFilter filter);

  // Customize the conditions under which the simulation is considered
  // complete. By default, uses DefaultExitConditions() as exit
  // conditions.  The supplied function is invoked after each
  // iterative step with the current state of the model, the current
  // time, and the last applied acceleration. The exit conditions
  // function receives a non-const pointer to the underlying state and
  // can modify it to enforce end conditions as necessary.
  void SetExitCondition(ExitConditionFunc exit_func);

  static bool DefaultExitCondition(State* state, const State& prev_state,
                                   double t, const Vector2f& a);

 private:
  struct Derivative {
    Vector2f dp;  // derivative of position: velocity
    Vector2f dv;  // derivative of velocity: acceleration
  };

  void AddFrictionalDeceleration(float mu);

  Derivative Evaluate(const State &initial, double t, double dt, const Derivative &d);

  // RK4 numerical integrator. Returns the acceleration at time t.
  Vector2f Integrate(State* state, double t, double dt);

 private:
  std::list<AccelerationFunc> accels_;
  std::list<AccelerationFilter> filters_;
  WallTime start_time_;
  WallTime last_time_;
  State state_;
  ExitConditionFunc exit_condition_;

  static const float kEpsilon_;
  static const double kDeltaTime_;
  static const double kMaxSimulationTime_;
};

#endif // VIEWFINDER_PHYSICS_MODEL_H
